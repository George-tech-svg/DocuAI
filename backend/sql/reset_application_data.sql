-- Permanently deletes DocuMind application records while keeping all tables,
-- columns, indexes, and the Alembic migration history intact.
-- Run this in the Neon SQL editor only when you intend to start over.
-- This script refuses to proceed if Cloudinary originals are still linked.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.documents
        WHERE cloudinary_public_id IS NOT NULL
        LIMIT 1
    ) THEN
        RAISE EXCEPTION
            'Reset stopped: documents still reference Cloudinary files. Delete those documents through the app first, then rerun this script.';
    END IF;
END
$$;

-- Child records first, so this remains safe even with legacy foreign keys.
DELETE FROM public.messages;
DELETE FROM public.document_chunks;
DELETE FROM public.documents;
DELETE FROM public.conversations;
DELETE FROM public.knowledge_bases;
DELETE FROM public.users;

COMMIT;
