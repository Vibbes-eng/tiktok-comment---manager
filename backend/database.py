# database.py - Module de gestion de la base de données
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    """
    Classe pour gérer la base de données SQLite
    (Peut être facilement adapté pour PostgreSQL ou MongoDB)
    """
    
    def __init__(self, db_path: str = "tiktok_comments.db"):
        """Initialiser la connexion à la base de données"""
        self.db_path = db_path
        self.conn = None
        logger.info(f"📁 Base de données: {db_path}")
    
    def get_connection(self):
        """Obtenir une connexion à la base de données"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Pour retourner des dict
        return self.conn
    
    def init_database(self):
        """Créer les tables si elles n'existent pas"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Table des comptes TikTok
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table des commentaires
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_url TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        """)
        
        # Table des statistiques (optionnel)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                date DATE DEFAULT CURRENT_DATE,
                comments_scraped INTEGER DEFAULT 0,
                comments_validated INTEGER DEFAULT 0,
                comments_published INTEGER DEFAULT 0,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        """)
        
        # Index pour améliorer les performances
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_status 
            ON comments(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_account 
            ON comments(account_id)
        """)
        
        conn.commit()
        logger.info("✅ Base de données initialisée")
    
    # ==================== GESTION DES COMPTES ====================
    
    def create_account(self, account_data: Dict) -> int:
        """
        Créer un nouveau compte TikTok
        
        Args:
            account_data: {username, active}
            
        Returns:
            int: ID du compte créé
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO accounts (username, active)
                VALUES (?, ?)
            """, (account_data['username'], account_data.get('active', False)))
            
            conn.commit()
            account_id = cursor.lastrowid
            logger.info(f"✅ Compte créé: {account_data['username']} (ID: {account_id})")
            return account_id
            
        except sqlite3.IntegrityError:
            logger.error(f"❌ Compte {account_data['username']} existe déjà")
            raise ValueError(f"Le compte {account_data['username']} existe déjà")
    
    def get_all_accounts(self) -> List[Dict]:
        """Récupérer tous les comptes"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """Récupérer un compte par ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        
        return dict(row) if row else None
    
    def update_account_status(self, account_id: int, active: bool):
        """Activer/désactiver un compte"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE accounts 
            SET active = ? 
            WHERE id = ?
        """, (active, account_id))
        
        conn.commit()
        logger.info(f"✅ Compte {account_id} {'activé' if active else 'désactivé'}")
    
    def delete_account(self, account_id: int):
        """Supprimer un compte"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Supprimer d'abord les commentaires associés
        cursor.execute("DELETE FROM comments WHERE account_id = ?", (account_id,))
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        
        conn.commit()
        logger.info(f"✅ Compte {account_id} supprimé")
    
    # ==================== GESTION DES COMMENTAIRES ====================
    
    def save_comment(self, comment_data: Dict) -> int:
        """
        Sauvegarder un commentaire
        
        Args:
            comment_data: {video_url, account_id, username, comment_text, ai_response, status}
            
        Returns:
            int: ID du commentaire créé
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO comments 
            (video_url, account_id, username, comment_text, ai_response, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            comment_data['video_url'],
            comment_data['account_id'],
            comment_data['username'],
            comment_data['comment_text'],
            comment_data['ai_response'],
            comment_data.get('status', 'pending')
        ))
        
        conn.commit()
        comment_id = cursor.lastrowid
        logger.info(f"✅ Commentaire sauvegardé (ID: {comment_id})")
        return comment_id
    
    def get_comments(
        self, 
        account_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Récupérer les commentaires avec filtres
        
        Args:
            account_id: Filtrer par compte (optionnel)
            status: Filtrer par statut (pending/validated/rejected/published)
            limit: Nombre maximum de résultats
            
        Returns:
            List[Dict]: Liste des commentaires
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM comments WHERE 1=1"
        params = []
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_comment(self, comment_id: int) -> Optional[Dict]:
        """Récupérer un commentaire par ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        
        return dict(row) if row else None
    
    def get_comments_by_ids(self, comment_ids: List[int]) -> List[Dict]:
        """Récupérer plusieurs commentaires par leurs IDs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(comment_ids))
        query = f"SELECT * FROM comments WHERE id IN ({placeholders})"
        
        cursor.execute(query, comment_ids)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def update_comment_status(self, comment_id: int, status: str):
        """
        Mettre à jour le statut d'un commentaire
        
        Args:
            comment_id: ID du commentaire
            status: Nouveau statut (pending/validated/rejected/published/failed)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE comments 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, comment_id))
        
        conn.commit()
        logger.info(f"✅ Commentaire {comment_id} -> {status}")
    
    def update_comment_response(self, comment_id: int, new_response: str, status: str = "validated"):
        """
        Modifier la réponse IA d'un commentaire
        
        Args:
            comment_id: ID du commentaire
            new_response: Nouvelle réponse
            status: Nouveau statut
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE comments 
            SET ai_response = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_response, status, comment_id))
        
        conn.commit()
        logger.info(f"✅ Réponse modifiée pour commentaire {comment_id}")
    
    def delete_comment(self, comment_id: int):
        """Supprimer un commentaire"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        logger.info(f"✅ Commentaire {comment_id} supprimé")
    
    # ==================== STATISTIQUES ====================
    
    def get_statistics(self, account_id: Optional[int] = None) -> Dict:
        """
        Récupérer les statistiques
        
        Args:
            account_id: Filtrer par compte (optionnel)
            
        Returns:
            Dict: Statistiques {total, pending, validated, rejected, published}
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT status, COUNT(*) as count FROM comments"
        params = []
        
        if account_id:
            query += " WHERE account_id = ?"
            params.append(account_id)
        
        query += " GROUP BY status"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        stats = {
            'total': 0,
            'pending': 0,
            'validated': 0,
            'rejected': 0,
            'published': 0,
            'failed': 0
        }
        
        for row in rows:
            status = row['status']
            count = row['count']
            stats[status] = count
            stats['total'] += count
        
        return stats
    
    def get_daily_statistics(self, account_id: Optional[int] = None, days: int = 7) -> List[Dict]:
        """
        Récupérer les statistiques par jour
        
        Args:
            account_id: Filtrer par compte (optionnel)
            days: Nombre de jours à récupérer
            
        Returns:
            List[Dict]: Statistiques par jour
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'validated' THEN 1 ELSE 0 END) as validated,
                SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published
            FROM comments
            WHERE created_at >= datetime('now', '-' || ? || ' days')
        """
        params = [days]
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        
        query += " GROUP BY DATE(created_at) ORDER BY date DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    # ==================== CLEANUP ====================
    
    def close(self):
        """Fermer la connexion à la base de données"""
        if self.conn:
            self.conn.close()
            logger.info("👋 Connexion DB fermée")

# Test unitaire
if __name__ == "__main__":
    # Tester la base de données
    db = Database("test_tiktok.db")
    db.init_database()
    
    try:
        # Créer un compte de test
        account_id = db.create_account({
            'username': '@soeurbonplan',
            'active': True
        })
        print(f"✅ Compte créé: ID {account_id}")
        
        # Sauvegarder un commentaire de test
        comment_id = db.save_comment({
            'video_url': 'https://tiktok.com/@test/video/123',
            'account_id': account_id,
            'username': 'test_user',
            'comment_text': 'Super vidéo!',
            'ai_response': 'Salam! Merci beaucoup 💕',
            'status': 'pending'
        })
        print(f"✅ Commentaire créé: ID {comment_id}")
        
        # Récupérer les statistiques
        stats = db.get_statistics()
        print(f"✅ Stats: {stats}")
        
        # Récupérer les comptes
        accounts = db.get_all_accounts()
        print(f"✅ Comptes: {accounts}")
        
    finally:
        db.close()
        print("✅ Test terminé")
