import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const withCredentials = import.meta.env.VITE_API_WITH_CREDENTIALS === "true";
const remoteUser = import.meta.env.VITE_REMOTE_USER ?? "";
const defaultHeaders = remoteUser ? { "X-Remote-User": remoteUser } : undefined;

export const api = axios.create({
  baseURL,
  timeout: 20000,
  withCredentials,
  headers: defaultHeaders,
});

function asArray(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.results)) return payload.results;
  if (Array.isArray(payload.data)) return payload.data;
  return [];
}

function normalizeSearchText(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u0131\u0130]/g, "i")
    .replace(/[\u00e7\u00c7]/g, "c")
    .replace(/[\u011f\u011e]/g, "g")
    .replace(/[\u00f6\u00d6]/g, "o")
    .replace(/[\u015f\u015e]/g, "s")
    .replace(/[\u00fc\u00dc]/g, "u")
    .toLowerCase()
    .trim();
}

function splitSearchTerms(value = "") {
  return normalizeSearchText(value)
    .split(/\s+/)
    .filter(Boolean);
}

function filterDirectoryRows(rows, query) {
  const uniqueRows = [];
  const seen = new Set();

  asArray(rows).forEach((item) => {
    const key = `${String(item?.username || "").trim().toLowerCase()}|${String(item?.displayName || "").trim().toLowerCase()}`;
    if (!item?.username || seen.has(key)) return;
    seen.add(key);
    uniqueRows.push(item);
  });

  const searchTerms = splitSearchTerms(query);
  if (!searchTerms.length) return uniqueRows;

  return uniqueRows.filter((item) => {
    const combined = normalizeSearchText([item.displayName, item.username, item.email].filter(Boolean).join(" "));
    if (!combined) return false;
    return searchTerms.every((term) => combined.includes(term));
  });
}

function normalizeDirectoryRows(payload) {
  return asArray(payload)
    .map((item) => {
      const email =
        item?.email ??
        item?.EMail ??
        item?.mail ??
        "";
      const explicitUsername =
        item?.username ??
        item?.Username ??
        item?.userName ??
        item?.UserName ??
        item?.sAMAccountName ??
        item?.samAccountName ??
        item?.userPrincipalName ??
        "";
      const derivedFromEmail =
        !explicitUsername && String(email || "").includes("@")
          ? String(email).split("@")[0]
          : "";
      const username = explicitUsername || derivedFromEmail;
      const displayName =
        item?.displayName ??
        item?.DisplayName ??
        item?.name ??
        "";
      return {
        username: String(username || "").trim(),
        displayName: String(displayName || "").trim(),
        email: String(email || "").trim(),
        id: item?.id ?? item?.Id ?? username ?? displayName,
      };
    })
    .filter((item) => item.username);
}

async function requestDirectoryUsers(query, signal) {
  const q = String(query ?? "").trim();
  if (q.length < 2) return [];

  const tryRequest = async (url, params) => {
    const response = await api.get(url, { params, signal });
    return normalizeDirectoryRows(response?.data ?? response);
  };

  let results = [];
  try {
    results = await tryRequest("/directory/search", { q });
    if (results.length) return results;
  } catch (error) {
    // swallow and continue with compatibility fallbacks
  }

  try {
    results = await tryRequest("/directory/search", { Prefix: q });
    if (results.length) return results;
  } catch (error) {
    // swallow and continue with compatibility fallbacks
  }

  try {
    results = await tryRequest("/AutoSuggestName", { Prefix: q });
    if (results.length) return results;
  } catch (error) {
    // bubble up only if all variants failed
    throw error;
  }

  return [];
}

export async function searchDirectoryUsers(query, options = {}) {
  const q = String(query ?? "").trim();
  if (q.length < 2) return [];
  const signal = options.signal;
  const queryVariants = [q];
  const tokenVariants = splitSearchTerms(q);
  if (tokenVariants.length > 1) queryVariants.push(...tokenVariants);

  const collected = [];
  let lastError = null;

  for (const variant of [...new Set(queryVariants)]) {
    try {
      const results = await requestDirectoryUsers(variant, signal);
      collected.push(...results);
    } catch (error) {
      lastError = error;
    }

    const filtered = filterDirectoryRows(collected, q);
    if (filtered.length) return filtered;
  }

  const filtered = filterDirectoryRows(collected, q);
  if (filtered.length) return filtered;
  if (lastError) throw lastError;
  return [];
}

