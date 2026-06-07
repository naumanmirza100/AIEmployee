/**
 * Extract a user-facing message from an API error.
 * Handles hard-block subscription errors (402/403) with the backend's
 * user_message, and falls back to a generic message for other errors.
 */
export function apiErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const isHardBlock =
    error?.status === 402 ||
    error?.status === 403 ||
    error?.data?.hard_block === true;

  if (isHardBlock) {
    return error?.data?.message || 'Your token quota has been exhausted. Please add a key or contact your admin.';
  }
  return error?.data?.message || error?.message || fallback;
}

/**
 * Returns toast props for an API error — handles quota/hard-block errors
 * with a longer duration and distinct title.
 * Usage: toast(toastForError(error, 'Failed to do X'))
 */
export function toastForError(error, fallback = 'Something went wrong. Please try again.') {
  const isQuota =
    error?.status === 402 ||
    error?.status === 403 ||
    error?.data?.hard_block === true;
  return {
    title: isQuota ? 'Token Limit Reached' : 'Error',
    description: apiErrorMessage(error, fallback),
    variant: 'destructive',
    duration: isQuota ? 8000 : 4000,
  };
}
