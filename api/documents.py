"""What Frontline and HR say about a document that has no text yet (12 Nov 2026 for Frontline, 19 Nov for HR).

A browser check on 19 Nov found HR's Summarize and Extract still answering "Document has no extracted text yet"
(400, shown as a red error) while the document was being read; Frontline had said "still being read" (409)
since 12 Nov. One answer for both now."""
from rest_framework import status
from rest_framework.response import Response


def no_text_yet(document, action):
    """Why a document has no text, in plain words. The text is saved when the background job has read the file
    (about two minutes for a 10 MB PDF), and Summarize used to say "no text content" during that time.
    Frontline's Document and HR's HRDocument alike: both keep processing_status and processing_error."""
    state = document.processing_status
    if state in ('pending', 'processing'):
        return Response({
            'status': 'error',
            'processing_status': state,
            'message': (f"This document is still being read, so it can't be {action} yet. Try again when its card "
                        "shows Indexed: usually within a minute, a few minutes for a large PDF."),
        }, status=status.HTTP_409_CONFLICT)
    if state == 'failed':
        reason = (document.processing_error or '').strip()
        return Response({
            'status': 'error',
            'processing_status': state,
            'message': ("This document could not be read" + (f" ({reason})" if reason else '')
                        + ". Press Retry on its card."),
        }, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        'status': 'error',
        'processing_status': state,
        'message': ("No text could be read from this document. A scanned picture without readable text, "
                    "for example; upload a copy with text in it."),
    }, status=status.HTTP_400_BAD_REQUEST)
