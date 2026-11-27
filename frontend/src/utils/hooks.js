import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

/** GET a resource and re-fetch when `params` change. Returns { data, loading, error, reload }.
 * Pass a null/empty path to skip the request (e.g. data only one mode or role needs). */
export function useApi(path, params) {
  const [state, setState] = useState({ data: null, loading: Boolean(path), error: null });
  const key = JSON.stringify(params || {});
  const seq = useRef(0);

  const load = useCallback(() => {
    const id = ++seq.current;
    if (!path) { setState({ data: null, loading: false, error: null }); return; }
    setState((s) => ({ ...s, loading: true, error: null }));
    api.get(path, params)
      .then((data) => id === seq.current && setState({ data, loading: false, error: null }))
      .catch((error) => id === seq.current && setState((s) => ({ ...s, loading: false, error })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);

  useEffect(load, [load]);

  // Coming back to this browser tab: quietly refresh, so changes made elsewhere (another tab, another
  // person accepting an invitation, a payment…) show without pressing reload.
  useEffect(() => {
    if (!path) return undefined;
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      const id = ++seq.current;
      api.get(path, params).then((data) => id === seq.current && setState({ data, loading: false, error: null })).catch(() => {});
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);

  return { ...state, reload: load };
}

/** Debounce a fast-changing value (e.g. a search box). */
export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/**
 * Run a write action (POST/PATCH…) with busy, error and success-notice state.
 * Resolves to the result, or to undefined if the action failed (the error is kept in `act.error`).
 * Usage: const act = useAction(); if (await act.run(() => api.post(...), "Saved.")) reload();
 */
export function useAction() {
  const [state, setState] = useState({ busy: false, error: null, notice: null });
  const run = useCallback(async (fn, notice = null) => {
    setState({ busy: true, error: null, notice: null });
    try {
      const result = await fn();
      setState({ busy: false, error: null, notice: typeof notice === "function" ? notice(result) : notice });
      return result;
    } catch (error) {
      setState({ busy: false, error, notice: null });
      return undefined;
    }
  }, []);
  const clear = useCallback(() => setState({ busy: false, error: null, notice: null }), []);
  const say = useCallback((notice) => setState({ busy: false, error: null, notice }), []); // show a success line
  return { ...state, run, clear, say };
}
