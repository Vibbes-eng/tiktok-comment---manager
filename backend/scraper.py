# scraper.py - Module Selenium pour TikTok
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import pyperclip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TikTokScraper:
    """
    Classe pour scraper et interagir avec TikTok via Selenium
    """
    
    def __init__(self, headless=False):
        """Initialiser le driver Selenium"""
        self.driver = None
        self.video_info = {}
        self.headless = headless
        self._init_driver()
    
    def _init_driver(self):
        """Configurer et initialiser le driver Chrome"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Chemin du ChromeDriver (à adapter selon votre système)
        # Option 1: ChromeDriver local
        # service = Service(executable_path='/path/to/chromedriver')
        
        # Option 2: Utiliser webdriver-manager (recommandé)
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("✅ Driver Selenium initialisé")
    
    def scrape_video(self, video_url: str):
        """
        Scraper tous les commentaires d'une vidéo TikTok
        
        Args:
            video_url: URL de la vidéo TikTok
            
        Returns:
            List[dict]: Liste des commentaires avec username et texte
        """
        try:
            logger.info(f"🔍 Scraping de la vidéo: {video_url}")
            self.driver.get(video_url)
            
            # Attendre le chargement de la page
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//div[@data-e2e='comment-item']"))
            )
            
            # Extraire les infos de la vidéo (titre, hashtags)
            self._extract_video_info()
            
            # Ouvrir les commentaires si nécessaire
            self._open_comments_section()
            
            # Charger tous les commentaires par scroll
            self._scroll_to_load_all_comments()
            
            # Extraire les commentaires
            comments_data = self._extract_comments()
            
            logger.info(f"✅ {len(comments_data)} commentaires scrapés")
            return comments_data
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du scraping: {e}")
            raise
    
    def _extract_video_info(self):
        """Extraire le titre et les hashtags de la vidéo"""
        try:
            # Titre de la vidéo
            selectors = [
                "//h1[@data-e2e='video-title']",
                "//h1[contains(@class, 'video-meta-title')]",
                "//span[@data-e2e='new-desc-span']"
            ]
            
            video_title = "Unknown Title"
            for selector in selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    video_title = element.text.strip()
                    if video_title:
                        break
                except NoSuchElementException:
                    continue
            
            # Hashtags
            hashtag_elements = []
            hashtag_selectors = [
                "//a[@data-e2e='browse-video-hashtag']",
                "//a[contains(@href, '/tag/')]"
            ]
            
            for selector in hashtag_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        hashtag_elements = elements
                        break
                except NoSuchElementException:
                    continue
            
            hashtags = [elem.text.strip() for elem in hashtag_elements]
            
            self.video_info = {
                'title': video_title,
                'hashtags': hashtags
            }
            
            logger.info(f"📹 Vidéo: {video_title}")
            logger.info(f"🏷️ Hashtags: {hashtags}")
            
        except Exception as e:
            logger.error(f"❌ Erreur extraction infos vidéo: {e}")
            self.video_info = {'title': 'Unknown', 'hashtags': []}
    
    def _open_comments_section(self):
        """Ouvrir la section des commentaires si elle est fermée"""
        try:
            comments_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@data-e2e='comment-icon']"))
            )
            comments_button.click()
            logger.info("💬 Section commentaires ouverte")
            time.sleep(2)
        except TimeoutException:
            logger.info("💬 Section commentaires déjà ouverte")
    
    def _scroll_to_load_all_comments(self):
        """Scroller pour charger tous les commentaires"""
        try:
            comment_container = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'DivCommentListContainer')]"))
            )
            
            logger.info("📜 Chargement de tous les commentaires...")
            last_height = self.driver.execute_script("return arguments[0].scrollHeight", comment_container)
            
            while True:
                # Scroller vers le bas
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", comment_container)
                time.sleep(2)
                
                # Calculer la nouvelle hauteur
                new_height = self.driver.execute_script("return arguments[0].scrollHeight", comment_container)
                
                if new_height == last_height:
                    break
                    
                last_height = new_height
            
            logger.info("✅ Tous les commentaires chargés")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du scroll: {e}")
    
    def _extract_comments(self):
        """
        Extraire tous les commentaires de la page
        Exclut automatiquement les commentaires de "Soeur bonplan 🎀"
        """
        try:
            comment_blocks = self.driver.find_elements(
                By.XPATH, 
                "//div[contains(@class, 'DivCommentContentWrapper')]"
            )
            
            comments_data = []
            excluded_username = "soeur bonplan 🎀"
            
            for i, comment_block in enumerate(comment_blocks, 1):
                try:
                    # Extraire le nom d'utilisateur
                    username = ""
                    try:
                        username_element = comment_block.find_element(
                            By.XPATH, 
                            ".//div[@data-e2e='comment-username-1']//a"
                        )
                        href = username_element.get_attribute("href")
                        if href and "/@" in href:
                            username = "@" + href.split("/@")[-1].split("?")[0]
                        else:
                            username = username_element.text.strip()
                    except NoSuchElementException:
                        pass
                    
                    # Essayer d'obtenir le display name
                    try:
                        display_name_element = comment_block.find_element(
                            By.XPATH, 
                            ".//p[contains(@class, 'TUXText') and contains(@class, 'weight-medium')]"
                        )
                        display_name = display_name_element.text.strip()
                        if display_name:
                            username = display_name
                    except NoSuchElementException:
                        pass
                    
                    # Extraire le texte du commentaire
                    comment_text = ""
                    try:
                        comment_text_element = comment_block.find_element(
                            By.XPATH, 
                            ".//span[@data-e2e='comment-level-1']/p"
                        )
                        comment_text = comment_text_element.text.strip()
                    except NoSuchElementException:
                        logger.warning(f"⚠️ Impossible de récupérer le texte du commentaire {i}")
                        continue
                    
                    # Exclure les commentaires de l'utilisateur principal
                    if username.lower().strip() == excluded_username.lower():
                        logger.info(f"⏭️ Commentaire exclu: {username}")
                        continue
                    
                    comments_data.append({
                        'username': username,
                        'comment_text': comment_text,
                        'comment_element': comment_block  # Garder pour la réponse
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Erreur extraction commentaire {i}: {e}")
                    continue
            
            return comments_data
            
        except Exception as e:
            logger.error(f"❌ Erreur extraction commentaires: {e}")
            return []
    
    def reply_to_comment(self, video_url: str, username: str, reply_text: str):
        """
        Répondre à un commentaire spécifique
        
        Args:
            video_url: URL de la vidéo
            username: Nom d'utilisateur du commentaire
            reply_text: Texte de la réponse
        """
        try:
            # Si pas déjà sur la page, y naviguer
            if self.driver.current_url != video_url:
                self.driver.get(video_url)
                time.sleep(3)
            
            # Trouver le commentaire de cet utilisateur
            comment_blocks = self.driver.find_elements(
                By.XPATH, 
                "//div[contains(@class, 'DivCommentContentWrapper')]"
            )
            
            target_comment = None
            for block in comment_blocks:
                try:
                    user_element = block.find_element(By.XPATH, ".//div[@data-e2e='comment-username-1']//a")
                    if username in user_element.text or username.replace('@', '') in user_element.get_attribute("href"):
                        target_comment = block
                        break
                except:
                    continue
            
            if not target_comment:
                raise Exception(f"Commentaire de {username} non trouvé")
            
            # Cliquer sur le bouton "Répondre"
            reply_button = target_comment.find_element(By.XPATH, ".//button[@data-e2e='reply-button']")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reply_button)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", reply_button)
            logger.info(f"💬 Bouton répondre cliqué pour @{username}")
            time.sleep(1)
            
            # Trouver le champ de réponse
            reply_input_selectors = [
                "//div[@class='public-DraftEditorPlaceholder-inner' and contains(text(), 'Ajouter une réponse')]/following::div[@contenteditable='true'][1]",
                "//div[@contenteditable='true' and @role='textbox']"
            ]
            
            reply_input = None
            for selector in reply_input_selectors:
                try:
                    reply_input = WebDriverWait(self.driver, 10).until(
                        EC.visibility_of_element_located((By.XPATH, selector))
                    )
                    if reply_input:
                        break
                except TimeoutException:
                    continue
            
            if not reply_input:
                raise Exception("Champ de réponse non trouvé")
            
            # Entrer la réponse
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reply_input)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", reply_input)
            time.sleep(0.5)
            
            # Utiliser pyperclip pour coller
            try:
                pyperclip.copy(reply_text)
                reply_input.send_keys(Keys.CONTROL, 'v')
            except:
                reply_input.send_keys(reply_text)
            
            logger.info(f"✍️ Réponse saisie: {reply_text[:50]}...")
            time.sleep(2)
            
            # Publier la réponse
            publish_buttons = self.driver.find_elements(
                By.XPATH, 
                "//div[@data-e2e='comment-post' and @role='button' and @aria-disabled='false']"
            )
            
            if len(publish_buttons) >= 2:
                publish_button = publish_buttons[1]
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", publish_button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", publish_button)
                logger.info(f"✅ Réponse publiée pour @{username}")
                time.sleep(3)
            else:
                raise Exception("Bouton publier non trouvé")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la réponse à @{username}: {e}")
            raise
    
    def get_video_info(self):
        """Retourner les infos de la vidéo actuelle"""
        return self.video_info
    
    def close(self):
        """Fermer le driver Selenium"""
        if self.driver:
            self.driver.quit()
            logger.info("👋 Driver Selenium fermé")

# Test unitaire
if __name__ == "__main__":
    scraper = TikTokScraper(headless=False)
    
    try:
        video_url = "https://www.tiktok.com/@soeurbonplan/video/7524405570321894678"
        comments = scraper.scrape_video(video_url)
        
        print(f"\n✅ {len(comments)} commentaires trouvés:")
        for comment in comments[:5]:  # Afficher les 5 premiers
            print(f"- @{comment['username']}: {comment['comment_text'][:50]}...")
        
    finally:
        scraper.close()
