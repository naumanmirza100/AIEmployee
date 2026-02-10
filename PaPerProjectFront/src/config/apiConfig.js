/**
 * Centralized API Configuration
 * 
 * This is the single point of configuration for the API base URL.
 * Change the DEFAULT_API_URL below to update the API endpoint for the entire application.
 * 
 * You can also override this by setting VITE_API_URL in your .env file:
 * VITE_API_URL=http://localhost:8000/api
 */

// Default API URL - Change this to update the API endpoint globally
const DEFAULT_API_URL = 'http://localhost:8000/api';

// Get API URL from environment variable or use default
export const API_BASE_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;

// Export for use in other files
export default API_BASE_URL;





