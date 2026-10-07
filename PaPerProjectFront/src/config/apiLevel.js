/**
 * The server API level these screens need.
 *
 * Raise this by one, and API_LEVEL in core/version.py to the same number, in
 * any change where the screens start needing something new from the server.
 * While the server is below it, people see ServerVersionNotice instead of
 * buttons that quietly fail. See core/version.py for the full story.
 */
export const REQUIRED_API_LEVEL = 5;
