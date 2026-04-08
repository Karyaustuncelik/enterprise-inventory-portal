import { useCallback, useEffect, useMemo, useState } from "react";
import { api, searchDirectoryUsers } from "../api";
import CustomSelect from "./CustomSelect";
import LoadingLogo from "./LoadingLogo";
import "./UsersPage.css";

const AUTH_USERNAME_DOMAIN = String(import.meta.env.VITE_AUTH_USERNAME_DOMAIN ?? "ENTERPRISE").trim();

function coerceArray(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function normalizeRoles(payload) {
  return coerceArray(payload).map((role) => {
    const id =
      role?.RoleId ??
      role?.roleId ??
      role?.id ??
      null;
    const name =
      role?.RoleName ??
      role?.roleName ??
      role?.name ??
      role?.label ??
      "";
    return id === null ? null : { id: Number(id), name: String(name || "").trim() || `Role ${id}` };
  }).filter(Boolean);
}

function stripDomain(value = "") {
  if (!value) return "";
  const segments = String(value).split("\\");
  return segments[segments.length - 1] || value;
}

function humanizeUsername(username = "") {
  const simple = stripDomain(username);
  if (!simple) return "";
  return simple
    .replace(/[._]/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");
}

function normalizeUserKey(value = "") {
  return stripDomain(value).toLowerCase();
}

function normalizeUsernameForSubmit(value = "") {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  if (raw.includes("\\") || raw.includes("@")) return raw;
  if (!AUTH_USERNAME_DOMAIN) return raw;
  return `${AUTH_USERNAME_DOMAIN}\\${raw}`;
}

function normalizeUsers(payload, roleMap) {
  return coerceArray(payload).map((item) => {
    const id = item?.Id ?? item?.id ?? null;
    const username = item?.Username ?? item?.username ?? item?.userName ?? "";
    const roleIdRaw = item?.Role ?? item?.role ?? item?.roleId ?? item?.RoleId ?? null;
    const roleId = roleIdRaw === null || roleIdRaw === undefined ? null : Number(roleIdRaw);
    const displayName =
      item?.DisplayName ??
      item?.displayName ??
      item?.FullName ??
      item?.fullName ??
      item?.Name ??
      item?.name ??
      "";
    const resolvedRoleName =
      roleMap.get(roleId) ??
      item?.RoleName ??
      item?.roleName ??
      "";
    return {
      id,
      username,
      displayName: String(displayName || "").trim(),
      roleId,
      roleName: String(resolvedRoleName || ""),
    };
  });
}

function buildManualCandidate(query = "") {
  const trimmed = String(query ?? "").trim();
  if (!trimmed) return null;
  const normalizedUsername = normalizeUsernameForSubmit(trimmed);
  return {
    username: normalizedUsername,
    displayName: "",
    id: normalizedUsername,
  };
}

export default function UsersPage({
  canManageUsers,
  currentUser,
  loadingCurrentUser,
}) {
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [roleUpdating, setRoleUpdating] = useState({});
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [directoryResults, setDirectoryResults] = useState([]);
  const [directoryLoading, setDirectoryLoading] = useState(false);
  const [directoryError, setDirectoryError] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [addRoleId, setAddRoleId] = useState("");
  const [addingUser, setAddingUser] = useState(false);
  const [deletingUserIds, setDeletingUserIds] = useState({});
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const selectMenuMaxHeight = 180;

  const roleMap = useMemo(() => new Map(roles.map((role) => [role.id, role.name])), [roles]);
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: String(role.id), label: role.name })),
    [roles]
  );
  const manualCandidate = useMemo(() => buildManualCandidate(addQuery), [addQuery]);
  const currentUserRaw = String(currentUser?.username ?? "").trim().toLowerCase();
  const currentUserShort = normalizeUserKey(currentUserRaw);

  const refreshUsers = useCallback(async () => {
    setError("");
    try {
      const response = await api.get("/users");
      const fetchedUsers = normalizeUsers(response.data ?? response, roleMap);
      setUsers(fetchedUsers);
    } catch (err) {
      console.error("/users error", err);
      setError("Failed to load users.");
    }
  }, [roleMap]);

  useEffect(() => {
    if (!canManageUsers) {
      setLoading(false);
      return;
    }
    let ignore = false;
    setLoading(true);
    setError("");

    Promise.all([
      api.get("/roles"),
      api.get("/users"),
    ])
      .then(([roleResponse, userResponse]) => {
        if (ignore) return;
        const roleList = normalizeRoles(roleResponse.data ?? roleResponse);
        const roleLookupLive = new Map(roleList.map((role) => [role.id, role.name]));
        const userListLive = normalizeUsers(userResponse.data ?? userResponse, roleLookupLive);
        setRoles(roleList);
        setUsers(userListLive);
      })
      .catch((err) => {
        if (ignore) return;
        console.error("bootstrap users error", err);
        setError("User data could not be loaded.");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [canManageUsers]);

  useEffect(() => {
    const timer = notice
      ? setTimeout(() => setNotice(""), 4000)
      : null;
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [notice]);

  useEffect(() => {
    if (!showAddPanel) {
      setDirectoryResults([]);
      setDirectoryError("");
      return;
    }
    if (selectedCandidate) {
      setDirectoryResults([]);
      setDirectoryError("");
      setDirectoryLoading(false);
      return;
    }
    const query = addQuery.trim();
    if (query.length < 2) {
      setDirectoryResults([]);
      setDirectoryError("");
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setDirectoryLoading(true);
      setDirectoryError("");
      searchDirectoryUsers(query, { signal: controller.signal })
        .then((results) => {
          setDirectoryResults(results);
          if (!results.length) {
            setDirectoryError("No matching users found. You can use the typed username.");
          }
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          console.error("/directory/search error", err);
          setDirectoryError("User search failed.");
        })
        .finally(() => {
          setDirectoryLoading(false);
        });
    }, 400);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [addQuery, selectedCandidate, showAddPanel]);

  useEffect(() => {
    if (!roles.length) return;
    setAddRoleId((prev) => (prev ? prev : String(roles[0].id)));
  }, [roles]);

  const handleRoleChange = useCallback((user, nextRoleIdRaw) => {
    const nextRoleId = Number(nextRoleIdRaw);
    if (!user?.id || Number(user.roleId) === nextRoleId) return;
    setRoleUpdating((prev) => ({ ...prev, [user.id]: true }));
    setError("");
    setNotice("");
    api.patch(`/users/${user.id}`, { roleId: nextRoleId })
      .then(() => {
        setUsers((prev) =>
          prev.map((item) =>
            item.id === user.id
              ? {
                  ...item,
                  roleId: nextRoleId,
                  roleName: roleMap.get(nextRoleId) ?? item.roleName,
                }
              : item
          )
        );
        const display = user.displayName || humanizeUsername(user.username);
        const roleLabel = roleMap.get(nextRoleId) ?? "selected role";
        setNotice(`${display} now has the ${roleLabel} role.`);
      })
      .catch((err) => {
        console.error("update user role error", err);
        setError("User role could not be updated. Please try again.");
      })
      .finally(() => {
        setRoleUpdating((prev) => {
          const next = { ...prev };
          delete next[user.id];
          return next;
        });
      });
  }, [roleMap]);

  const openDeleteConfirm = (user) => {
    if (!user?.id) return;
    setDeleteCandidate(user);
    setError("");
    setNotice("");
  };

  const closeDeleteConfirm = () => {
    setDeleteCandidate(null);
  };

  const handleDeleteUser = useCallback(async () => {
    if (!deleteCandidate?.id) return;
    const user = deleteCandidate;
    setDeletingUserIds((prev) => ({ ...prev, [user.id]: true }));
    setError("");
    setNotice("");
    try {
      await api.delete(`/users/${user.id}`);
      setUsers((prev) => prev.filter((item) => item.id !== user.id));
      setNotice(`${user.displayName || humanizeUsername(user.username)} deleted.`);
      setDeleteCandidate(null);
    } catch (err) {
      console.error("delete user error", err);
      const status = err?.response?.status;
      if (status === 404) {
        setError("User not found.");
      } else if (status === 401 || status === 403) {
        setError("You are not authorized.");
      } else {
        setError("User could not be deleted. Please try again.");
      }
    } finally {
      setDeletingUserIds((prev) => {
        const next = { ...prev };
        delete next[user.id];
        return next;
      });
    }
  }, [deleteCandidate]);

  const resetAddPanel = () => {
    setAddQuery("");
    setDirectoryResults([]);
    setSelectedCandidate(null);
    setDirectoryError("");
    setDirectoryLoading(false);
  };

  const handleOpenAddPanel = () => {
    setShowAddPanel(true);
    resetAddPanel();
  };

  const handleCloseAddPanel = () => {
    setShowAddPanel(false);
    resetAddPanel();
  };

  const handleAddUserSubmit = (event) => {
    event.preventDefault();
    const candidate = selectedCandidate ?? manualCandidate;
    if (!candidate || !addRoleId) {
      setError("Enter a username and select a role.");
      return;
    }
    const roleId = Number(addRoleId);
    setAddingUser(true);
    setError("");
    setNotice("");
    const normalizedUsername = normalizeUsernameForSubmit(candidate.username);
    if (!normalizedUsername) {
      setError("Enter a valid username.");
      setAddingUser(false);
      return;
    }
    const payload = {
      username: normalizedUsername,
      roleId,
    };
    if (candidate.displayName) {
      payload.displayName = candidate.displayName;
    }
    api.post("/users", payload)
      .then((response) => {
        const data = response?.data ?? response;
        if (data) {
          const normalized = normalizeUsers([data], roleMap)[0];
          if (normalized) {
            setUsers((prev) => {
              const exists = prev.some((item) => (item.username || "").toLowerCase() === normalized.username.toLowerCase());
              if (exists) {
                return prev.map((item) =>
                  (item.username || "").toLowerCase() === normalized.username.toLowerCase()
                    ? { ...item, ...normalized }
                    : item
                );
              }
              return [normalized, ...prev];
            });
          }
        }
        refreshUsers();
        const display = candidate.displayName || humanizeUsername(normalizedUsername);
        const roleLabel = roleMap.get(roleId) ?? "selected role";
        setNotice(`${display} added with the ${roleLabel} role.`);
        setSelectedCandidate(null);
        setAddQuery("");
        setDirectoryResults([]);
        setShowAddPanel(false);
        resetAddPanel();
      })
      .catch((err) => {
        console.error("add user error", err);
        setError("User could not be added. Check your permissions or network connection.");
      })
      .finally(() => {
        setAddingUser(false);
      });
  };

  const handleSelectSuggestion = (suggestion) => {
    setSelectedCandidate(suggestion);
    setAddQuery(suggestion.displayName || humanizeUsername(suggestion.username));
    setDirectoryResults([]);
    setDirectoryError("");
  };

  const handleQueryChange = (event) => {
    setAddQuery(event.target.value);
    setSelectedCandidate(null);
    setDirectoryError("");
  };

  if (!canManageUsers) {
    return (
      <section className="placeholder-section">
        <div className="placeholder-card">
          <span className="placeholder-eyebrow">Restricted</span>
          <h2>Users</h2>
          <p>
            {loadingCurrentUser
              ? "Loading your user profile..."
              : "You do not have access to this page."}
          </p>
        </div>
      </section>
    );
  }

  const canSubmitAdd = Boolean((selectedCandidate || manualCandidate) && addRoleId && !addingUser);
  const deleteInProgress = deleteCandidate ? Boolean(deletingUserIds[deleteCandidate.id]) : false;

  return (
    <section className="table-section users-section">
      <header className="table-header">
        <div>
          <h2>User access control</h2>
        </div>
        <div className="table-header-meta">
          <button
            type="button"
            className="add-circle-button"
            onClick={handleOpenAddPanel}
            aria-label="Add user"
            disabled={showAddPanel}
          >
            <span aria-hidden="true">+</span>
          </button>
        </div>
      </header>

      {notice ? <div className="form-notice" role="status">{notice}</div> : null}
      {error ? <div className="form-error" role="alert">{error}</div> : null}

      {showAddPanel ? (
        <div className="form-dialog-backdrop" role="dialog" aria-modal="true">
          <form className="users-add-card users-add-dialog" onSubmit={handleAddUserSubmit}>
            <h3 className="users-add-title">Add user</h3>
            <div className="users-field">
              <label htmlFor="user-search">User</label>
              <div className="users-person-input directory-input">
                <input
                  id="user-search"
                  type="text"
                  value={addQuery}
                  onChange={handleQueryChange}
                  placeholder="Type a name or DOMAIN\\username"
                  autoComplete="off"
                />
                {directoryLoading ? <span className="directory-hint">Searching...</span> : null}
                {directoryError && !directoryResults.length ? (
                  <span className="directory-hint directory-hint--error">{directoryError}</span>
                ) : null}
                {directoryResults.length ? (
                  <ul className="directory-suggestions custom-scrollbar" role="listbox">
                    {directoryResults.map((result) => (
                      <li
                        key={result.id}
                        className="directory-suggestion"
                        onMouseDown={() => handleSelectSuggestion(result)}
                        role="option"
                      >
                        <span className="directory-suggestion-name">{result.displayName || humanizeUsername(result.username)}</span>
                        <span className="directory-suggestion-meta">{result.username}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {selectedCandidate ? (
                  <div className="users-selected-user" aria-live="polite">
                    <span className="users-selected-user-name">
                      {selectedCandidate.displayName || humanizeUsername(selectedCandidate.username)}
                    </span>
                    <span className="users-selected-user-meta">{selectedCandidate.username}</span>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="users-field">
              <label htmlFor="user-role">Role</label>
              <CustomSelect
                id="user-role"
                options={roleOptions}
                value={addRoleId}
                onChange={(nextValue) => setAddRoleId(nextValue)}
                placeholder="Select role"
                disabled={!roleOptions.length || addingUser}
                menuMaxHeight={220}
              />
            </div>

            <div className="users-add-actions">
              <button type="button" className="ghost-button" onClick={handleCloseAddPanel} disabled={addingUser}>
                Cancel
              </button>
              <button type="submit" className="ghost-button primary" disabled={!canSubmitAdd}>
                {addingUser ? "Adding..." : "Add user"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {loading ? (
        <div className="table-placeholder table-placeholder--logo">
          <LoadingLogo label="Loading user list" size={112} />
        </div>
      ) : !users.length ? (
        <div className="table-placeholder">No user assignments found.</div>
      ) : (
        <div className="table-scroll users-table-scroll">
          <table className="data-table users-table">
            <thead>
              <tr>
                <th>Edit role</th>
                <th className="users-col-name">Name &amp; Surname</th>
                <th className="users-col-role">Role</th>
                <th className="users-col-actions">Delete user</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const isUpdating = Boolean(roleUpdating[user.id]);
                const roleSelectValue = user.roleId === null || user.roleId === undefined ? "" : String(user.roleId);
                const displayName = user.displayName || humanizeUsername(user.username);
                const roleLabel = user.roleName || roleMap.get(user.roleId) || "Unknown role";
                const isDeleting = Boolean(deletingUserIds[user.id]);
                const userRaw = String(user.username ?? "").trim().toLowerCase();
                const userShort = normalizeUserKey(userRaw);
                const isSelf = Boolean(currentUserRaw) && (userRaw === currentUserRaw || userShort === currentUserShort);
                const deleteDisabled = isDeleting || isSelf;
                const deleteLabel = isDeleting ? "Deleting..." : "Delete";
                return (
                  <tr key={user.id ?? user.username}>
                    <td>
                      <CustomSelect
                        options={roleOptions}
                        value={roleSelectValue}
                        onChange={(nextValue) => handleRoleChange(user, nextValue)}
                        placeholder="Select role"
                        disabled={isUpdating || !roleOptions.length}
                        menuMaxHeight={selectMenuMaxHeight}
                      />
                    </td>
                    <td className="users-cell-center">{displayName}</td>
                    <td className="users-cell-center">{roleLabel}</td>
                    <td className="users-cell-center">
                      <button
                        type="button"
                        className="users-delete-button"
                        onClick={() => openDeleteConfirm(user)}
                        disabled={deleteDisabled}
                        aria-label={`Delete user ${displayName}`}
                      >
                        {deleteLabel}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {deleteCandidate ? (
        <div className="form-dialog-backdrop" role="dialog" aria-modal="true">
          <div className="form-dialog-card">
            <h3>Delete user</h3>
            <p>This user will be deleted. Are you sure?</p>
            <div className="users-confirm-actions">
              <button
                type="button"
                className="ghost-button danger"
                onClick={handleDeleteUser}
                disabled={deleteInProgress}
              >
                {deleteInProgress ? "Deleting..." : "Delete user"}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={closeDeleteConfirm}
                disabled={deleteInProgress}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

