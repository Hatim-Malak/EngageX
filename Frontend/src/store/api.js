import axios from "axios";

const API_BASE_URL = import.meta.env.MODE === "development"
  ? 'http://localhost:8000'
  : "https://routinex-v2.onrender.com";

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 120_000, // 2 min — ingestion can be slow
});

// ── Response interceptor: normalise errors ──────────────────
api.interceptors.response.use(
  (res) => res,
  (error) => {
    // Extract the most useful message from FastAPI error shapes
    const detail = error.response?.data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? error.message ?? "Something went wrong";

    const normalised = {
      status: error.response?.status ?? 0,
      message,
      raw: detail,
    };

    return Promise.reject(normalised);
  }
);

export { API_BASE_URL };
export default api;
