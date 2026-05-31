import { create } from "zustand";
import { persist } from "zustand/middleware";
import api, { API_BASE_URL } from "./api";
import toast from "react-hot-toast";

// ═══════════════════════════════════════════════════════════════
//  useEngageStore — single Zustand store for the entire app
//
//  Slices:
//   • Ingestion   – submit two video URLs, track progress
//   • Session     – validate session, load metadata & engagement
//   • Chat        – query (streaming SSE) + conversation history
//   • Rate Limits – per-IP and per-session usage
// ═══════════════════════════════════════════════════════════════

const useEngageStore = create(
  persist(
    (set, get) => ({
  // ─────────────────────────────────────────────────────────────
  //  Session state
  // ─────────────────────────────────────────────────────────────
  sessionId: null,
  sessionExists: false,
  sessionLoading: false,

  // Video metadata returned by GET /api/session/:id
  videoA: null,
  videoB: null,
  engagement: null,

  // ─────────────────────────────────────────────────────────────
  //  Ingestion state
  // ─────────────────────────────────────────────────────────────
  ingesting: false,
  ingestResult: null, // full IngestResponse
  ingestError: null,

  // ─────────────────────────────────────────────────────────────
  //  Chat / Query state
  // ─────────────────────────────────────────────────────────────
  messages: [], // { role: 'user' | 'assistant', content, citations?, timestamp }
  streamingResponse: "", // partial response while SSE is active
  isStreaming: false,
  queryLoading: false,
  queryError: null,

  // ─────────────────────────────────────────────────────────────
  //  Rate-limit state
  // ─────────────────────────────────────────────────────────────
  rateLimits: null, // full object from GET /api/rate-limits
  queriesUsed: 0,
  queriesRemaining: 50,
  queriesLimit: 50,

  // ─────────────────────────────────────────────────────────────
  //  Global error
  // ─────────────────────────────────────────────────────────────
  error: null,
  clearError: () => set({ error: null }),

  // ═════════════════════════════════════════════════════════════
  //  ACTIONS
  // ═════════════════════════════════════════════════════════════

  // ── 1. Ingest two videos ──────────────────────────────────
  //    POST /api/ingest  { url_a, url_b }
  //    Then poll GET /api/ingest/status/{job_id}
  ingestVideos: async (urlA, urlB) => {
    set({
      ingesting: true,
      ingestError: null,
      ingestResult: null,
      error: null,
    });

    try {
      const { data } = await api.post("/ingest", {
        url_a: urlA,
        url_b: urlB,
      });

      const jobId = data.job_id;
      if (!jobId) {
        throw new Error("No job ID returned from ingestion.");
      }

      // Poll until finished or failed
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 3000)); // Poll every 3s
        
        const statusRes = await api.get(`/ingest/status/${jobId}`);
        const statusData = statusRes.data;

        if (statusData.status === "finished") {
          const result = statusData.result;
          
          set({
            ingesting: false,
            ingestResult: result,
            sessionId: result.session_id,
            sessionExists: true,
            engagement: {
              winner: result.engagement_winner,
              engagement_rate_a: result.engagement_rate_a,
              engagement_rate_b: result.engagement_rate_b,
            },
            queriesUsed: 0,
            queriesRemaining: 50,
          });

          toast.success("Videos ingested successfully!");
          return result;
        } else if (statusData.status === "failed") {
          throw new Error(statusData.error || "Ingestion failed during processing.");
        }
        // If status is queued, started, etc., keep polling
      }

    } catch (err) {
      const msg = err.message || "Ingestion failed";
      set({ ingesting: false, ingestError: msg, error: msg });
      
      toast.error(msg);
      throw err;
    }
  },

  // ── 2. Validate / load session ────────────────────────────
  //    GET /api/session/:id
  loadSession: async (sessionId) => {
    set({ sessionLoading: true, error: null });

    try {
      const { data } = await api.get(`/session/${sessionId}`);

      set({
        sessionLoading: false,
        sessionId,
        sessionExists: data.exists,
        videoA: data.video_a,
        videoB: data.video_b,
        engagement: data.engagement,
      });

      if (!data.exists) {
        toast.error("Session not found or expired.");
      }

      return data;
    } catch (err) {
      const msg = err.message || "Failed to load session";
      set({
        sessionLoading: false,
        sessionExists: false,
        error: msg,
      });
      toast.error(msg);
      return null;
    }
  },

  // ── 3. Load conversation history ──────────────────────────
  //    GET /api/session/:id/history
  loadHistory: async (sessionId) => {
    const id = sessionId || get().sessionId;
    if (!id) return;

    try {
      const { data } = await api.get(`/session/${id}/history`);
      const history = (data.history || []).map((msg) => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
      }));

      set({ messages: history });
      return history;
    } catch (err) {
      console.error("[loadHistory]", err);
      return [];
    }
  },

  // ── 4. Clear history (new conversation) ───────────────────
  //    DELETE /api/session/:id/history
  clearHistory: async (sessionId) => {
    const id = sessionId || get().sessionId;
    if (!id) return;

    try {
      await api.delete(`/session/${id}/history`);
      set({ messages: [], streamingResponse: "" });
      toast.success("Conversation cleared — videos still ingested.");
      return true;
    } catch (err) {
      toast.error(err.message || "Failed to clear history");
      return false;
    }
  },

  // ── 5. Send query (non-streaming) ────────────────────────
  //    POST /api/query  { session_id, user_query }
  sendQuery: async (userQuery) => {
    const { sessionId, messages } = get();
    if (!sessionId) {
      toast.error("No active session. Ingest videos first.");
      return null;
    }

    // Optimistic: add user message
    const userMsg = {
      role: "user",
      content: userQuery,
      timestamp: new Date().toISOString(),
    };
    set({
      messages: [...messages, userMsg],
      queryLoading: true,
      queryError: null,
    });

    try {
      const { data } = await api.post("/query", {
        session_id: sessionId,
        user_query: userQuery,
      });

      const assistantMsg = {
        role: "assistant",
        content: data.response,
        citations: data.citations || [],
        intent: data.intent,
        timestamp: new Date().toISOString(),
      };

      set((s) => ({
        messages: [...s.messages, assistantMsg],
        queryLoading: false,
        queriesUsed: data.queries_used,
        queriesRemaining: data.queries_remaining,
      }));

      return data;
    } catch (err) {
      const msg = err.message || "Query failed";
      set({ queryLoading: false, queryError: msg });

      if (err.status === 429) {
        toast.error("Query limit reached for today.");
      } else {
        toast.error(msg);
      }
      return null;
    }
  },

  // ── 6. Streaming query via SSE ────────────────────────────
  //    POST /api/query/stream  { session_id, user_query }
  //
  //    SSE protocol:
  //      data: [RATELIMIT]{...}     → rate limit info (first)
  //      data: <word>               → token
  //      data: [CITATIONS]{...}     → citations array
  //      data: [DONE]               → end
  //      data: [ERROR]{...}         → error
  sendStreamQuery: async (userQuery) => {
    const { sessionId, messages } = get();
    if (!sessionId) {
      toast.error("No active session. Ingest videos first.");
      return;
    }

    // Optimistic: add user message
    const userMsg = {
      role: "user",
      content: userQuery,
      timestamp: new Date().toISOString(),
    };
    set({
      messages: [...messages, userMsg],
      isStreaming: true,
      streamingResponse: "",
      queryError: null,
    });

    let fullResponse = "";
    let citations = [];
    let abortController = new AbortController();

    // Store abort fn so UI can cancel
    set({ _abortStream: () => abortController.abort() });

    try {
      const response = await fetch(`${API_BASE_URL}/api/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_query: userQuery,
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        const detail = errBody.detail;
        throw {
          status: response.status,
          message:
            typeof detail === "string"
              ? detail
              : detail?.message ?? "Stream request failed",
        };
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6); // strip "data: "

          // ── [RATELIMIT] ─────────────────────────────────
          if (payload.startsWith("[RATELIMIT]")) {
            try {
              const rl = JSON.parse(payload.slice(11));
              set({
                queriesUsed: rl.used,
                queriesRemaining: rl.remaining,
                queriesLimit: rl.limit,
              });
            } catch {
              /* ignore parse errors */
            }
            continue;
          }

          // ── [CITATIONS] ────────────────────────────────
          if (payload.startsWith("[CITATIONS]")) {
            try {
              citations = JSON.parse(payload.slice(11));
            } catch {
              /* ignore */
            }
            continue;
          }

          // ── [DONE] ─────────────────────────────────────
          if (payload === "[DONE]") {
            break;
          }

          // ── [ERROR] ────────────────────────────────────
          if (payload.startsWith("[ERROR]")) {
            try {
              const errObj = JSON.parse(payload.slice(7));
              toast.error(errObj.error || "Streaming error");
            } catch {
              toast.error("Streaming error");
            }
            continue;
          }

          // ── Normal token ───────────────────────────────
          let tokenText = payload;
          if (payload.startsWith('{"text":')) {
            try {
              tokenText = JSON.parse(payload).text;
            } catch (e) {}
          }
          
          fullResponse += tokenText;
          set({ streamingResponse: fullResponse });
        }
      }

      // Finalise: add assistant message to history
      const assistantMsg = {
        role: "assistant",
        content: fullResponse,
        citations,
        timestamp: new Date().toISOString(),
      };

      set((s) => ({
        messages: [...s.messages, assistantMsg],
        isStreaming: false,
        streamingResponse: "",
        _abortStream: null,
      }));
    } catch (err) {
      if (err.name === "AbortError") {
        // User cancelled — keep what we have so far
        if (fullResponse) {
          set((s) => ({
            messages: [
              ...s.messages,
              {
                role: "assistant",
                content: fullResponse + " _(cancelled)_",
                citations,
                timestamp: new Date().toISOString(),
              },
            ],
          }));
        }
      } else {
        const msg = err.message || "Streaming failed";
        set({ queryError: msg });

        if (err.status === 429) {
          toast.error("Query limit reached for today.");
        } else {
          toast.error(msg);
        }
      }

      set({ isStreaming: false, streamingResponse: "", _abortStream: null });
    }
  },

  // ── 7. Abort active stream ────────────────────────────────
  abortStream: () => {
    const abort = get()._abortStream;
    if (abort) abort();
  },

  // ── 8. Fetch rate-limit status ────────────────────────────
  //    GET /api/rate-limits?session_id=...
  fetchRateLimits: async () => {
    const { sessionId } = get();
    const params = sessionId ? `?session_id=${sessionId}` : "";

    try {
      const { data } = await api.get(`/rate-limits${params}`);
      set({
        rateLimits: data,
        ...(data.session && {
          queriesUsed: data.session.used_today,
          queriesRemaining: data.session.remaining,
          queriesLimit: data.session.limit,
        }),
      });
      return data;
    } catch (err) {
      console.error("[fetchRateLimits]", err);
      return null;
    }
  },

  // ── 9. Health check ───────────────────────────────────────
  //    GET /api/health
  healthCheck: async () => {
    try {
      const { data } = await api.get("/health");
      return data;
    } catch {
      return null;
    }
  },

  // ── 10. Reset store ───────────────────────────────────────
  //    Called when user wants to start fresh
  resetStore: () =>
    set({
      sessionId: null,
      sessionExists: false,
      sessionLoading: false,
      videoA: null,
      videoB: null,
      engagement: null,
      ingesting: false,
      ingestResult: null,
      ingestError: null,
      messages: [],
      streamingResponse: "",
      isStreaming: false,
      queryLoading: false,
      queryError: null,
      rateLimits: null,
      queriesUsed: 0,
      queriesRemaining: 50,
      queriesLimit: 50,
      error: null,
    }),

  // ── Internal (not for UI) ─────────────────────────────────
  _abortStream: null,
    }),
    {
      name: "engagex-store",
      // Only persist the state that should survive a page reload.
      // Transient flags (ingesting, isStreaming, etc.) reset to defaults.
      partialize: (state) => ({
        sessionId: state.sessionId,
        sessionExists: state.sessionExists,
        videoA: state.videoA,
        videoB: state.videoB,
        engagement: state.engagement,
        messages: state.messages,
        queriesUsed: state.queriesUsed,
        queriesRemaining: state.queriesRemaining,
        queriesLimit: state.queriesLimit,
      }),
    }
  )
);

export default useEngageStore;
