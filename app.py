# app.py - Backend FastAPI principal
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
from datetime import datetime

# Imports locaux
from scraper import TikTokScraper
from ai_handler import AIResponseGenerator
from database import Database

# ==================== CONFIGURATION ====================
app = FastAPI(title="TikTok Comment Manager API", version="1.0.0")

# CORS pour permettre les requêtes du frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production: mettre l'URL exacte du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialisation des services
db = Database()
ai_generator = AIResponseGenerator()
scraper = None  # Initialisé à la demande (Selenium coûteux)

# ==================== MODELS PYDANTIC ====================
class VideoURL(BaseModel):
    url: str
    account_id: int

class CommentResponse(BaseModel):
    comment_id: int
    username: str
    comment_text: str
    ai_response: str
    status: str = "pending"
    video_url: str

class ValidateComment(BaseModel):
    comment_id: int
    action: str  # "validate", "reject", "modify"
    modified_response: Optional[str] = None

class PublishRequest(BaseModel):
    comment_ids: List[int]
    account_id: int

class TikTokAccount(BaseModel):
    username: str
    active: bool = False

class UpdateComment(BaseModel):
    comment_id: int
    ai_response: str

# ==================== ROUTES API ====================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "running",
        "message": "TikTok Comment Manager API",
        "version": "1.0.0"
    }

@app.post("/api/scrape")
async def scrape_video(video_data: VideoURL, background_tasks: BackgroundTasks):
    """
    Scraper une vidéo TikTok et générer les réponses IA
    """
    try:
        # Vérifier que le compte existe et est actif
        account = db.get_account(video_data.account_id)
        if not account or not account['active']:
            raise HTTPException(status_code=400, detail="Compte non actif ou inexistant")
        
        # Lancer le scraping en arrière-plan
        background_tasks.add_task(
            process_video_scraping,
            video_data.url,
            video_data.account_id
        )
        
        return {
            "status": "processing",
            "message": "Le scraping a démarré. Cela peut prendre 1-2 minutes.",
            "video_url": video_data.url
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de scraping: {str(e)}")

async def process_video_scraping(video_url: str, account_id: int):
    """
    Fonction de traitement en arrière-plan du scraping
    """
    global scraper
    
    try:
        # Initialiser Selenium
        if not scraper:
            scraper = TikTokScraper()
        
        # Scraper les commentaires
        comments_data = scraper.scrape_video(video_url)
        
        if not comments_data:
            print(f"Aucun commentaire trouvé pour {video_url}")
            return
        
        # Extraire infos vidéo
        video_info = scraper.get_video_info()
        
        # Générer les réponses IA en batch
        ai_responses = ai_generator.generate_batch_responses(
            comments_data,
            video_info['title'],
            video_info['hashtags']
        )
        
        # Sauvegarder dans la base de données
        for comment, ai_response in zip(comments_data, ai_responses):
            db.save_comment({
                'video_url': video_url,
                'account_id': account_id,
                'username': comment['username'],
                'comment_text': comment['comment_text'],
                'ai_response': ai_response,
                'status': 'pending',
                'created_at': datetime.now()
            })
        
        print(f"✅ Scraping terminé: {len(comments_data)} commentaires traités")
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping: {e}")
    finally:
        # Fermer Selenium si besoin
        if scraper:
            scraper.close()
            scraper = None

@app.get("/api/comments")
async def get_comments(
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """
    Récupérer les commentaires avec filtres optionnels
    """
    try:
        comments = db.get_comments(
            account_id=account_id,
            status=status,
            limit=limit
        )
        return {
            "count": len(comments),
            "comments": comments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.post("/api/comments/validate")
async def validate_comment(validation: ValidateComment):
    """
    Valider, rejeter ou modifier un commentaire
    """
    try:
        comment = db.get_comment(validation.comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Commentaire non trouvé")
        
        # Mettre à jour le statut
        if validation.action == "validate":
            db.update_comment_status(validation.comment_id, "validated")
        elif validation.action == "reject":
            db.update_comment_status(validation.comment_id, "rejected")
        elif validation.action == "modify" and validation.modified_response:
            db.update_comment_response(
                validation.comment_id,
                validation.modified_response,
                "validated"
            )
        
        return {
            "status": "success",
            "comment_id": validation.comment_id,
            "action": validation.action
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.post("/api/comments/publish")
async def publish_comments(publish_data: PublishRequest, background_tasks: BackgroundTasks):
    """
    Publier les commentaires validés sur TikTok
    """
    try:
        # Vérifier que tous les commentaires sont validés
        comments = db.get_comments_by_ids(publish_data.comment_ids)
        
        invalid_comments = [c for c in comments if c['status'] != 'validated']
        if invalid_comments:
            raise HTTPException(
                status_code=400,
                detail=f"{len(invalid_comments)} commentaires non validés"
            )
        
        # Lancer la publication en arrière-plan
        background_tasks.add_task(
            process_comment_publishing,
            publish_data.comment_ids,
            publish_data.account_id
        )
        
        return {
            "status": "processing",
            "message": f"Publication de {len(publish_data.comment_ids)} commentaires en cours",
            "comment_count": len(publish_data.comment_ids)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

async def process_comment_publishing(comment_ids: List[int], account_id: int):
    """
    Fonction de traitement en arrière-plan de la publication
    """
    global scraper
    
    try:
        if not scraper:
            scraper = TikTokScraper()
        
        # Récupérer les commentaires à publier
        comments = db.get_comments_by_ids(comment_ids)
        
        # Publier chaque commentaire
        success_count = 0
        for comment in comments:
            try:
                scraper.reply_to_comment(
                    comment['video_url'],
                    comment['username'],
                    comment['ai_response']
                )
                db.update_comment_status(comment['id'], 'published')
                success_count += 1
                print(f"✅ Commentaire publié pour @{comment['username']}")
            except Exception as e:
                print(f"❌ Échec publication pour @{comment['username']}: {e}")
                db.update_comment_status(comment['id'], 'failed')
        
        print(f"✅ Publication terminée: {success_count}/{len(comments)} réussies")
        
    except Exception as e:
        print(f"❌ Erreur lors de la publication: {e}")
    finally:
        if scraper:
            scraper.close()
            scraper = None

@app.get("/api/accounts")
async def get_accounts():
    """
    Récupérer tous les comptes TikTok
    """
    try:
        accounts = db.get_all_accounts()
        return {"accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.post("/api/accounts")
async def create_account(account: TikTokAccount):
    """
    Ajouter un nouveau compte TikTok
    """
    try:
        account_id = db.create_account(account.dict())
        return {
            "status": "success",
            "account_id": account_id,
            "username": account.username
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int):
    """
    Supprimer un compte TikTok
    """
    try:
        db.delete_account(account_id)
        return {"status": "success", "message": "Compte supprimé"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.patch("/api/accounts/{account_id}")
async def toggle_account(account_id: int, active: bool):
    """
    Activer/désactiver un compte
    """
    try:
        db.update_account_status(account_id, active)
        return {
            "status": "success",
            "account_id": account_id,
            "active": active
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.get("/api/stats")
async def get_statistics(account_id: Optional[int] = None):
    """
    Récupérer les statistiques
    """
    try:
        stats = db.get_statistics(account_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.get("/api/export/excel")
async def export_to_excel(account_id: Optional[int] = None):
    """
    Exporter les données en Excel
    """
    try:
        import pandas as pd
        from io import BytesIO
        from fastapi.responses import StreamingResponse
        
        comments = db.get_comments(account_id=account_id, limit=1000)
        
        df = pd.DataFrame(comments)
        
        # Créer le fichier Excel en mémoire
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Comments', index=False)
        
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=tiktok_comments.xlsx"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur export: {str(e)}")

# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialisation au démarrage"""
    print("🚀 API TikTok Comment Manager démarrée")
    db.init_database()

@app.on_event("shutdown")
async def shutdown_event():
    """Nettoyage à l'arrêt"""
    global scraper
    if scraper:
        scraper.close()
    print("👋 API arrêtée proprement")

# ==================== LANCEMENT ====================

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Désactiver en production
    )
