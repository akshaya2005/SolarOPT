import { useState, useEffect } from 'react';

// In-memory cache across hook lifecycles
const dataCache = new Map();

/**
 * Custom hook to load precomputed solar optimization data for a selected location.
 * Uses Vite's public asset path respecting import.meta.env.BASE_URL.
 * Employs standard AbortController for clean lifecycle cancellation.
 *
 * @param {string} fileName - e.g. "miami_fl.json"
 * @returns {{ data: Object|null, loading: boolean, error: string|null }}
 */
export function useSolarData(fileName) {
  const [state, setState] = useState(() => ({
    data: dataCache.get(fileName) || null,
    loading: Boolean(fileName && !dataCache.has(fileName)),
    error: null,
    fileName,
  }));

  // Update synchronously during render if fileName changes and data is cached
  if (state.fileName !== fileName) {
    if (dataCache.has(fileName)) {
      setState({
        data: dataCache.get(fileName),
        loading: false,
        error: null,
        fileName,
      });
    } else {
      setState({
        data: null,
        loading: Boolean(fileName),
        error: null,
        fileName,
      });
    }
  }

  useEffect(() => {
    if (!fileName || dataCache.has(fileName)) return;

    const abortController = new AbortController();

    async function fetchData() {
      try {
        const baseUrl = import.meta.env.BASE_URL || '/';
        const normalizedBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
        const url = `${normalizedBase}data/${fileName}`;

        const response = await fetch(url, { signal: abortController.signal });
        if (!response.ok) {
          throw new Error(`Failed to load dataset (${response.status} ${response.statusText})`);
        }

        const json = await response.json();

        // Validate data contract schema
        if (json.schema_version !== '1.0') {
          throw new Error(`Unsupported schema version "${json.schema_version}". Expected "1.0".`);
        }
        if (!Array.isArray(json.configurations) || json.configurations.length === 0) {
          throw new Error('Invalid bundle: missing or empty configurations array.');
        }
        if (!json.recommendation || !json.metadata) {
          throw new Error('Invalid bundle: missing metadata or recommendation object.');
        }

        dataCache.set(fileName, json);
        setState({
          data: json,
          loading: false,
          error: null,
          fileName,
        });
      } catch (err) {
        if (err.name === 'AbortError') return;
        setState({
          data: null,
          loading: false,
          error: err.message || 'Error loading solar optimization data',
          fileName,
        });
      }
    }

    fetchData();

    return () => {
      abortController.abort();
    };
  }, [fileName]);

  return { data: state.data, loading: state.loading, error: state.error };
}
