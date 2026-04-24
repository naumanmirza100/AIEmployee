"""
Management command to generate embeddings for existing documents via RAG chunks
Usage: python manage.py generate_embeddings [--company-id COMPANY_ID] [--all]
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from Frontline_agent.models import Document, DocumentChunk
from core.Frontline_agent.embedding_service import EmbeddingService
import logging
import json

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate overlapping chunk embeddings for documents'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            help='Only process documents for a specific company',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all documents, even those that already have chunks',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of documents to process',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        process_all = options.get('all', False)
        limit = options.get('limit')
        
        embedding_service = EmbeddingService()
        
        if not embedding_service.is_available():
            self.stdout.write(
                self.style.ERROR('Embedding service is not available. Please check API keys.')
            )
            return
        
        # Build query
        query = Document.objects.filter(
            is_indexed=True,
            processed=True
        ).exclude(document_content='')
        
        if company_id:
            query = query.filter(company_id=company_id)
        
        if not process_all:
            # Only process documents that have NO chunks
            doc_ids_with_chunks = DocumentChunk.objects.values_list('document_id', flat=True).distinct()
            query = query.exclude(id__in=doc_ids_with_chunks)
        
        if limit:
            query = query[:limit]
        
        documents = list(query)
        total = len(documents)
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No documents to process.'))
            return
        
        self.stdout.write(f'Processing {total} document(s)...')
        
        success_count = 0
        error_count = 0
        
        for i, doc in enumerate(documents, 1):
            try:
                # Create searchable text
                searchable_text = f"{doc.title}\n{doc.description}\n{doc.document_content}".strip()
                
                if not searchable_text:
                    self.stdout.write(
                        self.style.WARNING(f'[{i}/{total}] Skipping document {doc.id} (empty content)')
                    )
                    continue
                    
                # Delete existing chunks if processing all
                if process_all:
                    doc.chunks.all().delete()
                
                # Chunking logic
                chunk_size = 4000
                overlap = 200
                chunks = []
                start = 0
                while start < len(searchable_text):
                    end = start + chunk_size
                    chunks.append(searchable_text[start:end])
                    start += chunk_size - overlap
                
                # Batch process
                batch_size = 20
                for j in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[j:j+batch_size]
                    embeddings = embedding_service.generate_embeddings_batch(batch_chunks)
                    
                    for k, (chunk_text, embedding) in enumerate(zip(batch_chunks, embeddings)):
                        DocumentChunk.objects.create(
                            document=doc,
                            chunk_index=j+k,
                            chunk_text=chunk_text,
                            embedding=json.dumps(embedding) if embedding else None
                        )
                
                doc.embedding_model = embedding_service.embedding_model
                doc.save(update_fields=['embedding_model'])

                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'[{i}/{total}] Generated {len(chunks)} chunks for document {doc.id}: "{doc.title}"')
                )
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing document {doc.id}: {e}", exc_info=True)
                self.stdout.write(
                    self.style.ERROR(f'[{i}/{total}] Error processing document {doc.id}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Completed: {success_count} succeeded, {error_count} failed out of {total} total'))

