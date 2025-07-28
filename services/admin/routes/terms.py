# services/admin/routes/terms.py

from datetime import datetime
from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.database import Database, get_db

terms_router = APIRouter()


# Pydantic models for Terms Management
class TermsDocumentCreate(BaseModel):
    document_type: str = Field(..., pattern="^(terms_of_service|privacy_policy)$")
    version: str = Field(..., max_length=20)
    content_url: str
    requires_acceptance: bool = True
    effective_date: str  # ISO date string


class TermsDocument(BaseModel):
    id: str
    document_type: str
    version: str
    title: str
    content_url: str
    content_hash: str
    is_active: bool
    requires_acceptance: bool
    effective_date: str
    created_by: str
    created_at: str


class UserTermsAcceptance(BaseModel):
    id: str
    user_id: str
    document_id: str
    document_type: str
    document_version: str
    accepted_at: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    acceptance_method: str


class TermsComplianceStats(BaseModel):
    total_documents: int
    active_documents: int
    total_acceptances: int
    compliance_rate: float
    recent_acceptances: list[UserTermsAcceptance]


@terms_router.get("/documents", response_model=list[TermsDocument])
async def get_terms_documents(
    admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    """Get all terms documents"""
    try:
        documents = await db.fetch_all(
            """
            SELECT td.*, u.fairyname as created_by_name
            FROM terms_documents td
            LEFT JOIN users u ON td.created_by = u.id
            ORDER BY td.document_type, td.created_at DESC
            """
        )

        return [
            TermsDocument(
                id=str(doc["id"]),
                document_type=doc["document_type"],
                version=doc["version"],
                title=doc["title"],
                content_url=doc["content_url"],
                content_hash=doc["content_hash"],
                is_active=doc["is_active"],
                requires_acceptance=doc["requires_acceptance"],
                effective_date=doc["effective_date"].isoformat(),
                created_by=doc["created_by_name"] or "Unknown",
                created_at=doc["created_at"].isoformat(),
            )
            for doc in documents
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch terms documents: {str(e)}")


@terms_router.post("/documents", response_model=TermsDocument)
async def create_terms_document(
    document: TermsDocumentCreate,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Create a new terms document"""
    try:
        # Check if version already exists for this document type
        existing = await db.fetch_one(
            """
            SELECT id FROM terms_documents
            WHERE document_type = $1 AND version = $2
            """,
            document.document_type,
            document.version,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Version {document.version} already exists for {document.document_type}",
            )

        # Parse effective date
        try:
            effective_date = datetime.fromisoformat(document.effective_date)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid effective_date format. Use YYYY-MM-DD"
            )

        # Auto-generate title based on document type and version
        if document.document_type == "terms_of_service":
            title = f"fairydust Terms of Service v{document.version}"
        else:  # privacy_policy
            title = f"fairydust Privacy Policy v{document.version}"

        # Auto-generate content hash based on URL + version + timestamp for uniqueness
        import hashlib
        import time

        hash_input = f"{document.content_url}_{document.version}_{int(time.time())}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Create document
        new_doc = await db.fetch_one(
            """
            INSERT INTO terms_documents (
                document_type, version, title, content_url, content_hash,
                requires_acceptance, effective_date, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            document.document_type,
            document.version,
            title,
            document.content_url,
            content_hash,
            document.requires_acceptance,
            effective_date,
            admin_user["user_id"],
        )

        return TermsDocument(
            id=str(new_doc["id"]),
            document_type=new_doc["document_type"],
            version=new_doc["version"],
            title=new_doc["title"],
            content_url=new_doc["content_url"],
            content_hash=new_doc["content_hash"],
            is_active=new_doc["is_active"],
            requires_acceptance=new_doc["requires_acceptance"],
            effective_date=new_doc["effective_date"].isoformat(),
            created_by=admin_user["fairyname"],
            created_at=new_doc["created_at"].isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create terms document: {str(e)}")


@terms_router.post("/documents/{document_id}/activate")
async def activate_terms_document(
    document_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Activate a terms document (deactivates others of same type)"""
    try:
        # Get the document to activate
        document = await db.fetch_one("SELECT * FROM terms_documents WHERE id = $1", document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Terms document not found")

        # Deactivate other documents of the same type
        await db.execute(
            """
            UPDATE terms_documents
            SET is_active = false
            WHERE document_type = $1 AND id != $2
            """,
            document["document_type"],
            document_id,
        )

        # Activate this document
        await db.execute("UPDATE terms_documents SET is_active = true WHERE id = $1", document_id)

        return {"message": "Terms document activated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate terms document: {str(e)}")


@terms_router.post("/documents/{document_id}/deactivate")
async def deactivate_terms_document(
    document_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Deactivate a terms document"""
    try:
        result = await db.execute(
            "UPDATE terms_documents SET is_active = false WHERE id = $1", document_id
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Terms document not found")

        return {"message": "Terms document deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to deactivate terms document: {str(e)}"
        )


@terms_router.get("/documents/{document_id}/acceptances", response_model=list[UserTermsAcceptance])
async def get_terms_acceptances(
    document_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get user acceptances for a specific document"""
    try:
        acceptances = await db.fetch_all(
            """
            SELECT uta.*, u.fairyname, td.document_type, td.version as document_version
            FROM user_terms_acceptance uta
            JOIN terms_documents td ON uta.document_id = td.id
            LEFT JOIN users u ON uta.user_id = u.id
            WHERE uta.document_id = $1
            ORDER BY uta.accepted_at DESC
            LIMIT 100
            """,
            document_id,
        )

        return [
            UserTermsAcceptance(
                id=str(acc["id"]),
                user_id=acc["fairyname"] or str(acc["user_id"]),  # Show fairyname instead of UUID
                document_id=str(acc["document_id"]),
                document_type=acc["document_type"],
                document_version=acc["document_version"],
                accepted_at=acc["accepted_at"].isoformat(),
                ip_address=acc["ip_address"],
                user_agent=acc["user_agent"],
                acceptance_method=acc["acceptance_method"],
            )
            for acc in acceptances
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch terms acceptances: {str(e)}")


@terms_router.get("/stats", response_model=TermsComplianceStats)
async def get_terms_stats(
    admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    """Get terms compliance statistics"""
    try:
        # Get document counts
        doc_stats = await db.fetch_one(
            """
            SELECT
                COUNT(*) as total_documents,
                COUNT(*) FILTER (WHERE is_active = true) as active_documents
            FROM terms_documents
            """
        )

        # Get total acceptances
        acceptance_stats = await db.fetch_one(
            "SELECT COUNT(*) as total_acceptances FROM user_terms_acceptance"
        )

        # Get user count for compliance rate calculation
        user_count = await db.fetch_one("SELECT COUNT(*) as total_users FROM users")

        # Calculate compliance rate (users who accepted any terms / total users)
        users_with_acceptances = await db.fetch_one(
            "SELECT COUNT(DISTINCT user_id) as users_with_acceptances FROM user_terms_acceptance"
        )

        compliance_rate = 0.0
        if user_count["total_users"] > 0:
            compliance_rate = (
                users_with_acceptances["users_with_acceptances"] / user_count["total_users"]
            ) * 100

        # Get recent acceptances
        recent_acceptances = await db.fetch_all(
            """
            SELECT uta.*, u.fairyname, td.document_type, td.version as document_version
            FROM user_terms_acceptance uta
            JOIN terms_documents td ON uta.document_id = td.id
            LEFT JOIN users u ON uta.user_id = u.id
            ORDER BY uta.accepted_at DESC
            LIMIT 10
            """
        )

        recent_acceptances_list = [
            UserTermsAcceptance(
                id=str(acc["id"]),
                user_id=acc["fairyname"] or str(acc["user_id"]),
                document_id=str(acc["document_id"]),
                document_type=acc["document_type"],
                document_version=acc["document_version"],
                accepted_at=acc["accepted_at"].isoformat(),
                ip_address=acc["ip_address"],
                user_agent=acc["user_agent"],
                acceptance_method=acc["acceptance_method"],
            )
            for acc in recent_acceptances
        ]

        return TermsComplianceStats(
            total_documents=doc_stats["total_documents"],
            active_documents=doc_stats["active_documents"],
            total_acceptances=acceptance_stats["total_acceptances"],
            compliance_rate=compliance_rate,
            recent_acceptances=recent_acceptances_list,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch terms stats: {str(e)}")
