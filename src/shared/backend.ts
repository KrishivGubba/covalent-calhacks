export const FLASK_PORT = import.meta.env.VITE_FLASK_PORT ?? '15001';
export const BACKEND_URL = `http://localhost:${FLASK_PORT}`;
