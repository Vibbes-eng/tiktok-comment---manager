# ai_handler.py - Module pour gérer les appels OpenAI
import os
import json
import logging
from typing import List, Dict
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIResponseGenerator:
    """
    Classe pour générer des réponses IA aux commentaires TikTok
    """
    
    def __init__(self):
        """Initialiser le client OpenAI"""
        # IMPORTANT: Stocker la clé API dans une variable d'environnement
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError(
                "⚠️ OPENAI_API_KEY non trouvée. "
                "Définissez la variable d'environnement: export OPENAI_API_KEY='sk-...'"
            )
        
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        logger.info(f"✅ Client OpenAI initialisé (modèle: {self.model})")
    
    def generate_batch_responses(
        self, 
        comments_data: List[Dict], 
        video_title: str, 
        hashtags: List[str]
    ) -> List[str]:
        """
        Générer des réponses IA pour tous les commentaires en un seul appel
        
        Args:
            comments_data: Liste des commentaires [{username, comment_text}, ...]
            video_title: Titre de la vidéo
            hashtags: Liste des hashtags
            
        Returns:
            List[str]: Liste des réponses IA correspondantes
        """
        if not comments_data:
            logger.warning("Aucun commentaire à traiter")
            return []
        
        try:
            logger.info(f"🤖 Génération de {len(comments_data)} réponses IA...")
            
            # Construire le prompt batch
            prompt = self._build_batch_prompt(comments_data, video_title, hashtags)
            
            # Appeler l'API OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "Tu es un assistant qui retourne uniquement du JSON valide."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=4000,
                temperature=0.7,
            )
            
            # Parser la réponse JSON
            response_text = response.choices[0].message.content.strip()
            logger.info(f"📥 Réponse API reçue ({len(response_text)} caractères)")
            
            # Nettoyer et parser le JSON
            parsed_responses = self._parse_json_response(response_text)
            
            if len(parsed_responses) != len(comments_data):
                logger.warning(
                    f"⚠️ Nombre de réponses ({len(parsed_responses)}) "
                    f"différent du nombre de commentaires ({len(comments_data)})"
                )
            
            logger.info(f"✅ {len(parsed_responses)} réponses générées avec succès")
            return parsed_responses
            
        except Exception as e:
            logger.error(f"❌ Erreur génération réponses IA: {e}")
            # Retourner des réponses par défaut en cas d'erreur
            return [
                "Salam! Merci pour ton commentaire 💕" 
                for _ in comments_data
            ]
    
    def _build_batch_prompt(
        self, 
        comments_data: List[Dict], 
        video_title: str, 
        hashtags: List[str]
    ) -> str:
        """Construire le prompt pour le batch de commentaires"""
        
        hashtags_str = ', '.join(hashtags) if hashtags else 'Aucun hashtag'
        
        prompt = f"""Tu es Copywriter GPT, un copywriter chaleureux et empathique pour TikTok. Tu réponds aux commentaires sur les vidéos de "Soeur Bon Plan 🎀", une créatrice de contenu lifestyle musulmane.

CONTEXTE DE LA VIDÉO:
- Titre: '{video_title}'
- Hashtags: {hashtags_str}
- Audience cible: Communauté musulmane féminine sur TikTok
- Objectif: Créer de l'engagement authentique et chaleureux

INSTRUCTIONS IMPORTANTES:
- Réponds à chaque commentaire avec MAXIMUM 114 caractères
- Commence par "Salam [nom]" ou simplement "Salam" si le nom est long
- Ton chaleureux, amical, comme une grande sœur bienveillante
- Utilise des expressions musulmanes légères (hamdoulillah, inshallah, Macha'Allah, Amine) de façon naturelle
- Ne donne JAMAIS de conseils médicaux, juridiques ou religieux précis
- Évite les questions ouvertes qui créent des débats
- Reste positive, encourageante et authentique
- Utilise des emojis appropriés (💕 🎀 ✨ 💖) mais avec modération

COMMENTAIRES À TRAITER:
"""
        
        # Ajouter chaque commentaire
        for i, comment in enumerate(comments_data, 1):
            prompt += f"\n{i}. Utilisateur: {comment['username']} | Commentaire: \"{comment['comment_text']}\""
        
        prompt += """

RÉPONSE ATTENDUE:
Retourne UNIQUEMENT un JSON valide avec ce format exact (sans markdown, sans backticks):
{
    "responses": [
        {"comment_id": 1, "username": "nom_utilisateur", "comment_text": "texte_commentaire", "chatgpt_response": "ta_réponse_114_chars_max"},
        {"comment_id": 2, "username": "nom_utilisateur", "comment_text": "texte_commentaire", "chatgpt_response": "ta_réponse_114_chars_max"}
    ]
}

RAPPEL CRITIQUE: Chaque réponse doit faire MAXIMUM 114 caractères!
"""
        
        return prompt
    
    def _parse_json_response(self, response_text: str) -> List[str]:
        """
        Parser la réponse JSON de l'API
        
        Args:
            response_text: Texte brut de la réponse
            
        Returns:
            List[str]: Liste des réponses extraites
        """
        try:
            # Nettoyer le texte (enlever les markdown backticks si présents)
            cleaned_text = response_text.strip()
            
            if "```json" in cleaned_text:
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0]
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.split("```")[1].split("```")[0]
            
            cleaned_text = cleaned_text.strip()
            
            # Parser le JSON
            parsed_data = json.loads(cleaned_text)
            
            # Extraire les réponses
            responses = parsed_data.get("responses", [])
            
            # Retourner uniquement les textes de réponse
            return [
                item.get("chatgpt_response", "Salam! Merci 💕") 
                for item in responses
            ]
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur parsing JSON: {e}")
            logger.error(f"Texte reçu: {response_text[:500]}...")
            raise
    
    def generate_single_response(
        self, 
        username: str, 
        comment_text: str, 
        video_title: str, 
        hashtags: List[str]
    ) -> str:
        """
        Générer une réponse unique pour un commentaire
        (Utilisé pour les modifications manuelles)
        
        Args:
            username: Nom d'utilisateur
            comment_text: Texte du commentaire
            video_title: Titre de la vidéo
            hashtags: Liste des hashtags
            
        Returns:
            str: Réponse générée
        """
        try:
            hashtags_str = ', '.join(hashtags) if hashtags else 'Aucun hashtag'
            
            prompt = f"""Tu es Copywriter GPT pour "Soeur Bon Plan 🎀".

CONTEXTE:
- Vidéo: '{video_title}'
- Hashtags: {hashtags_str}

COMMENTAIRE:
Utilisateur: {username}
Commentaire: "{comment_text}"

INSTRUCTIONS:
- Réponds en MAXIMUM 114 caractères
- Commence par "Salam {username}" ou "Salam"
- Ton chaleureux de grande sœur
- Utilise expressions musulmanes naturelles
- Pas de conseils médicaux/juridiques/religieux précis

Retourne UNIQUEMENT la réponse (pas de JSON, juste le texte de la réponse)."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Tu es un copywriter TikTok chaleureux et empathique."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7,
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Vérifier la longueur
            if len(ai_response) > 114:
                logger.warning(f"⚠️ Réponse trop longue ({len(ai_response)} chars), troncature...")
                ai_response = ai_response[:111] + "..."
            
            return ai_response
            
        except Exception as e:
            logger.error(f"❌ Erreur génération réponse unique: {e}")
            return f"Salam {username}! Merci pour ton message 💕"
    
    def validate_response_length(self, response: str, max_length: int = 114) -> bool:
        """
        Valider que la réponse respecte la limite de caractères
        
        Args:
            response: Texte de la réponse
            max_length: Longueur maximale autorisée
            
        Returns:
            bool: True si valide, False sinon
        """
        return len(response) <= max_length
    
    def truncate_response(self, response: str, max_length: int = 114) -> str:
        """
        Tronquer une réponse si elle dépasse la limite
        
        Args:
            response: Texte de la réponse
            max_length: Longueur maximale
            
        Returns:
            str: Réponse tronquée
        """
        if len(response) <= max_length:
            return response
        
        return response[:max_length - 3] + "..."

# Test unitaire
if __name__ == "__main__":
    # Pour tester, définir OPENAI_API_KEY dans l'environnement
    # export OPENAI_API_KEY="sk-..."
    
    try:
        ai_handler = AIResponseGenerator()
        
        # Test avec quelques commentaires
        test_comments = [
            {
                'username': 'fatima_dz',
                'comment_text': 'MashaAllah super vidéo! Où tu as acheté ça?'
            },
            {
                'username': 'muslima_paris',
                'comment_text': 'Baraka Allahou fik pour le partage ma sœur'
            }
        ]
        
        video_title = "Mes bons plans du mois"
        hashtags = ['#bonplan', '#muslim', '#lifestyle']
        
        responses = ai_handler.generate_batch_responses(
            test_comments, 
            video_title, 
            hashtags
        )
        
        print("\n✅ Réponses générées:")
        for comment, response in zip(test_comments, responses):
            print(f"\n@{comment['username']}: {comment['comment_text']}")
            print(f"→ {response} ({len(response)} chars)")
        
    except Exception as e:
        print(f"❌ Erreur test: {e}")
        print("Assurez-vous que OPENAI_API_KEY est définie dans l'environnement")
