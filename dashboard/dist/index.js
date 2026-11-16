(function () {
  "use strict";

  if (typeof window === "undefined") {
    return;
  }

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var REGISTRY = window.__HERMES_PLUGINS__;
  if (!SDK || !SDK.React || !REGISTRY || typeof REGISTRY.register !== "function") {
    return;
  }

  var React = SDK.React;
  var e = React.createElement;
  var useState = (SDK.hooks && SDK.hooks.useState) || React.useState;
  var useEffect = (SDK.hooks && SDK.hooks.useEffect) || React.useEffect;

  function fetchJson(path, opts) {
    if (typeof SDK.fetchJSON === "function") {
      return SDK.fetchJSON(path, opts);
    }
    return fetch(path, opts).then(function (res) {
      if (!res.ok) {
        throw new Error("HTTP " + res.status + " " + res.statusText);
      }
      return res.json();
    });
  }

  var STATUS_FILTERS = ["all", "intent", "ok", "deduped", "recovered_landed", "resumed", "error"];

  var STATUS_COLORS = {
    ok: "#10b981",
    committed: "#10b981",
    deduped: "#06b6d4",
    recovered_landed: "#f59e0b",
    resumed: "#f59e0b",
    intent: "#f59e0b",
    error: "#ef4444"
  };

  function statusColor(status) {
    return STATUS_COLORS[status] || "#9ca3af";
  }

  function formatJson(value) {
    if (value === undefined || value === null || value === "") {
      return "—";
    }
    if (typeof value === "string") {
      try {
        return JSON.stringify(JSON.parse(value), null, 2);
      } catch (_err) {
        return value;
      }
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch (_err2) {
      return String(value);
    }
  }

  function formatRelativeTime(ts) {
    if (!ts) {
      return "just now";
    }
    var ms = typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : Date.parse(ts);
    if (isNaN(ms)) {
      return String(ts);
    }
    var diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
    if (diffSec < 60) {
      return diffSec + "s ago";
    }
    if (diffSec < 3600) {
      return Math.floor(diffSec / 60) + "m ago";
    }
    if (diffSec < 86400) {
      return Math.floor(diffSec / 3600) + "h ago";
    }
    return Math.floor(diffSec / 86400) + "d ago";
  }

  function getEventLatencyMs(ev) {
    if (typeof ev.latency_ms === "number") {
      return ev.latency_ms;
    }
    if (typeof ev.duration_ms === "number") {
      return Math.max(0, Math.round(ev.duration_ms));
    }
    if (typeof ev.ts_done === "number" && typeof ev.ts_intent === "number") {
      return Math.max(0, Math.round((ev.ts_done - ev.ts_intent) * 1000));
    }
    return null;
  }

  function computeFpComparison(ev) {
    var pre = ev.pre_fp || ev.pre_fp_json || null;
    var post = ev.post_fp || ev.post_fp_json || null;
    if (!pre || !post) {
      return { verdict: "PENDING", color: "#f59e0b", pre: pre, post: post };
    }
    var preStr = typeof pre === "string" ? pre : JSON.stringify(pre);
    var postStr = typeof post === "string" ? post : JSON.stringify(post);
    if (preStr === postStr) {
      return { verdict: "MATCH", color: "#10b981", pre: preStr, post: postStr };
    }
    if (ev.status === "error") {
      return { verdict: "MUTATED", color: "#ef4444", pre: preStr, post: postStr };
    }
    if (ev.status === "recovered_landed") {
      return { verdict: "LANDED", color: "#f59e0b", pre: preStr, post: postStr };
    }
    return { verdict: "UPDATED", color: "#06b6d4", pre: preStr, post: postStr };
  }

  function normalizeEvents(timelineData, statusData) {
    if (Array.isArray(timelineData)) {
      return timelineData;
    }
    if (timelineData && Array.isArray(timelineData.items)) {
      return timelineData.items;
    }
    if (timelineData && Array.isArray(timelineData.events)) {
      return timelineData.events;
    }
    if (timelineData && Array.isArray(timelineData.timeline)) {
      return timelineData.timeline;
    }
    if (statusData && Array.isArray(statusData.timeline)) {
      return statusData.timeline;
    }
    if (statusData && Array.isArray(statusData.events)) {
      return statusData.events;
    }
    return [];
  }

  function copyText(text, onDone) {
    if (!text || text === "—") {
      return;
    }
    if (navigator && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard.writeText(String(text)).then(onDone).catch(function () {});
    }
  }

  function PhoenixDashboardPanel() {
    var statusHook = useState({ loading: true, data: null, error: null });
    var statusState = statusHook[0];
    var setStatusState = statusHook[1];

    var timelineHook = useState([]);
    var timelineEvents = timelineHook[0];
    var setTimelineEvents = timelineHook[1];

    var searchHook = useState("");
    var search = searchHook[0];
    var setSearch = searchHook[1];

    var filterHook = useState("all");
    var statusFilter = filterHook[0];
    var setStatusFilter = filterHook[1];

    var selectedHook = useState(null);
    var selectedId = selectedHook[0];
    var setSelectedId = selectedHook[1];

    var copiedHook = useState("");
    var copiedKey = copiedHook[0];
    var setCopiedKey = copiedHook[1];

    var wtHook = useState({ running: false, report: null, error: null });
    var wtState = wtHook[0];
    var setWtState = wtHook[1];

    var fetchAll = function () {
      fetchJson("/api/plugins/phoenix/status")
        .then(function (payload) {
          setStatusState({ loading: false, data: payload, error: null });
        })
        .catch(function (err) {
          setStatusState(function (prev) {
            return { loading: false, data: prev.data, error: (err && err.message) || String(err) };
          });
        });

      fetchJson("/api/plugins/phoenix/timeline")
        .then(function (payload) {
          if (payload) {
            setTimelineEvents(normalizeEvents(payload, null));
          }
        })
        .catch(function () {});
    };

    var runWindTunnel = function () {
      setWtState(function (prev) {
        return { running: true, report: prev.report, error: null };
      });
      fetchJson("/api/plugins/phoenix/windtunnel", { method: "POST" })
        .then(function (payload) {
          var unwrapped = payload && payload.report ? payload.report : payload;
          setWtState({ running: false, report: unwrapped, error: null });
          fetchAll();
        })
        .catch(function (err) {
          setWtState(function (prev) {
            return { running: false, report: prev.report, error: (err && err.message) || String(err) };
          });
        });
    };

    useEffect(function () {
      fetchAll();
      var interval = setInterval(fetchAll, 5000);
      return function () {
        clearInterval(interval);
      };
    }, []);

    var containerStyle = {
      padding: "20px",
      color: "var(--ui-text, #f3f4f6)",
      backgroundColor: "var(--ui-bg, #090d16)",
      borderRadius: "12px",
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      minHeight: "480px"
    };

    var headerStyle = {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: "16px",
      paddingBottom: "14px",
      borderBottom: "1px solid var(--ui-border, #1f293d)",
      flexWrap: "wrap",
      gap: "10px"
    };

    var btnStyle = {
      backgroundColor: "var(--ui-surface, #1f293d)",
      color: "var(--ui-text, #e5e7eb)",
      border: "1px solid var(--ui-border, #374151)",
      borderRadius: "6px",
      padding: "6px 12px",
      fontSize: "12px",
      fontWeight: 600,
      cursor: "pointer"
    };

    if (statusState.loading && !statusState.data) {
      return e(
        "div",
        { style: containerStyle },
        e("div", { style: headerStyle }, e("strong", null, "Phoenix Flight Recorder")),
        e("div", { style: { padding: "40px", textAlign: "center", color: "#9ca3af" } }, "Loading Phoenix WAL state...")
      );
    }

    if (statusState.error && !statusState.data) {
      return e(
        "div",
        { style: containerStyle },
        e("div", { style: headerStyle }, e("strong", null, "Phoenix Flight Recorder")),
        e(
          "div",
          {
            style: {
              padding: "14px",
              backgroundColor: "rgba(239, 68, 68, 0.15)",
              border: "1px solid rgba(239, 68, 68, 0.4)",
              borderRadius: "8px",
              color: "#fca5a5"
            }
          },
          "Failed to load Phoenix status: " + statusState.error
        ),
        e("button", { type: "button", style: Object.assign({}, btnStyle, { marginTop: "12px" }), onClick: fetchAll }, "Retry")
      );
    }

    var data = statusState.data || {};
    var stats = data.stats || data;
    var guardOn = Boolean(data.guard_enabled !== undefined ? data.guard_enabled : true);
    var events = timelineEvents.length > 0 ? timelineEvents : normalizeEvents(null, data);
    var recoveredCount = typeof data.recovered_landed === "number"
      ? data.recovered_landed
      : (typeof stats.recovered_landed === "number"
          ? stats.recovered_landed
          : events.filter(function (ev) { return ev.status === "recovered_landed"; }).length);

    var q = search.trim().toLowerCase();
    var filteredEvents = events.filter(function (ev) {
      if (statusFilter !== "all" && ev.status !== statusFilter) {
        return false;
      }
      if (!q) {
        return true;
      }
      var hay = [
        ev.tool,
        ev.tool_name,
        ev.op_id,
        ev.attempt_id,
        ev.idem_key,
        ev.idempotency_key,
        ev.status,
        typeof ev.args === "string" ? ev.args : JSON.stringify(ev.args || "")
      ].filter(Boolean).join(" ").toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    var selectedEvent = null;
    if (filteredEvents.length > 0) {
      if (selectedId) {
        for (var i = 0; i < filteredEvents.length; i += 1) {
          var cand = filteredEvents[i];
          if ((cand.attempt_id || cand.op_id) === selectedId) {
            selectedEvent = cand;
            break;
          }
        }
      }
      if (!selectedEvent) {
        selectedEvent = filteredEvents[0];
      }
    }

    var makeCard = function (label, value, color) {
      return e(
        "div",
        {
          key: label,
          style: {
            backgroundColor: "var(--ui-surface, #111827)",
            border: "1px solid var(--ui-border, #1f293d)",
            borderRadius: "8px",
            padding: "12px 14px"
          }
        },
        e(
          "div",
          {
            style: {
              fontSize: "11px",
              fontWeight: 600,
              color: "#9ca3af",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "4px"
            }
          },
          label
        ),
        e(
          "div",
          {
            style: {
              fontSize: "22px",
              fontWeight: 800,
              color: color || "#ffffff"
            }
          },
          String(value)
        )
      );
    };

    var wtReport = wtState.report || data.windtunnel_report || null;
    var wtChecks = wtReport && Array.isArray(wtReport.checks) ? wtReport.checks : [];
    var minimized = wtReport && (wtReport.ddmin || wtReport.minimized_trace || wtReport.ddmin_trace || wtReport.counterexample);

    var renderInspector = function () {
      if (!selectedEvent) {
        return e(
          "div",
          { style: { padding: "32px", textAlign: "center", color: "#9ca3af", fontSize: "13px" } },
          "Select a WAL event to inspect redacted args, idempotency key, SHA-256 fingerprints, and outcome."
        );
      }

      var fp = computeFpComparison(selectedEvent);
      var attemptId = selectedEvent.attempt_id || "—";
      var idempKey = selectedEvent.idem_key || selectedEvent.idempotency_key || selectedEvent.op_id || "—";
      var latency = getEventLatencyMs(selectedEvent);
      var argsPayload = selectedEvent.args !== undefined ? selectedEvent.args : selectedEvent.args_json;
      var resultPayload = selectedEvent.result !== undefined ? selectedEvent.result : selectedEvent.result_json;

      return e(
        "div",
        { style: { padding: "14px", display: "flex", flexDirection: "column", gap: "12px" } },
        e(
          "div",
          { style: { display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" } },
          e(
            "div",
            { style: { display: "flex", alignItems: "center", gap: "8px" } },
            e("span", { style: { width: "8px", height: "8px", borderRadius: "50%", backgroundColor: statusColor(selectedEvent.status), display: "inline-block" } }),
            e("strong", { style: { fontFamily: "monospace", fontSize: "14px" } }, selectedEvent.tool || selectedEvent.tool_name || "tool"),
            e(
              "span",
              {
                style: {
                  fontSize: "11px",
                  padding: "2px 8px",
                  borderRadius: "999px",
                  border: "1px solid " + statusColor(selectedEvent.status),
                  color: statusColor(selectedEvent.status)
                }
              },
              selectedEvent.status || "unknown"
            )
          ),
          e(
            "span",
            { style: { fontSize: "12px", color: "#9ca3af" } },
            (latency !== null ? latency + "ms · " : "") + formatRelativeTime(selectedEvent.ts_done || selectedEvent.ts_intent || selectedEvent.timestamp)
          )
        ),
        e(
          "div",
          { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "8px" } },
          e(
            "div",
            { style: { backgroundColor: "#0b1220", border: "1px solid #1f293d", borderRadius: "6px", padding: "8px 10px" } },
            e(
              "div",
              { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" } },
              e("span", { style: { fontSize: "10px", color: "#9ca3af", fontWeight: 700 } }, "ATTEMPT ID"),
              e(
                "button",
                {
                  type: "button",
                  style: Object.assign({}, btnStyle, { padding: "2px 6px", fontSize: "10px" }),
                  onClick: function () {
                    copyText(attemptId, function () { setCopiedKey("attempt"); });
                  }
                },
                copiedKey === "attempt" ? "Copied" : "Copy"
              )
            ),
            e("div", { style: { fontFamily: "monospace", fontSize: "11px", wordBreak: "break-all" } }, attemptId)
          ),
          e(
            "div",
            { style: { backgroundColor: "#0b1220", border: "1px solid #1f293d", borderRadius: "6px", padding: "8px 10px" } },
            e(
              "div",
              { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" } },
              e("span", { style: { fontSize: "10px", color: "#9ca3af", fontWeight: 700 } }, "OP ID / IDEMPOTENCY KEY"),
              e(
                "button",
                {
                  type: "button",
                  style: Object.assign({}, btnStyle, { padding: "2px 6px", fontSize: "10px" }),
                  onClick: function () {
                    copyText(idempKey, function () { setCopiedKey("op"); });
                  }
                },
                copiedKey === "op" ? "Copied" : "Copy"
              )
            ),
            e("div", { style: { fontFamily: "monospace", fontSize: "11px", wordBreak: "break-all" } }, idempKey)
          )
        ),
        e(
          "div",
          { style: { backgroundColor: "#0b1220", border: "1px solid #1f293d", borderRadius: "6px", padding: "10px" } },
          e(
            "div",
            { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" } },
            e("span", { style: { fontSize: "12px", fontWeight: 600 } }, "SHA-256 Fingerprint Diff (pre_fp vs post_fp)"),
            e("span", { style: { fontSize: "11px", fontWeight: 700, color: fp.color } }, fp.verdict)
          ),
          e(
            "div",
            { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontFamily: "monospace", fontSize: "11px" } },
            e("div", { style: { padding: "6px", backgroundColor: "#111827", borderRadius: "4px", wordBreak: "break-all" } }, "pre_fp: " + (fp.pre ? formatJson(fp.pre) : "—")),
            e("div", { style: { padding: "6px", backgroundColor: "#111827", borderRadius: "4px", wordBreak: "break-all" } }, "post_fp: " + (fp.post ? formatJson(fp.post) : "—"))
          )
        ),
        e(
          "div",
          { style: { backgroundColor: "#0b1220", border: "1px solid #1f293d", borderRadius: "6px", padding: "10px" } },
          e("div", { style: { fontSize: "11px", fontWeight: 600, color: "#9ca3af", marginBottom: "4px" } }, "Redacted Arguments"),
          e("pre", { style: { margin: 0, fontSize: "11px", whiteSpace: "pre-wrap", wordBreak: "break-word" } }, formatJson(argsPayload))
        ),
        e(
          "div",
          { style: { backgroundColor: "#0b1220", border: "1px solid #1f293d", borderRadius: "6px", padding: "10px" } },
          e("div", { style: { fontSize: "11px", fontWeight: 600, color: "#9ca3af", marginBottom: "4px" } }, selectedEvent.error ? "Error Outcome" : "Result Outcome"),
          e(
            "pre",
            { style: { margin: 0, fontSize: "11px", whiteSpace: "pre-wrap", wordBreak: "break-word", color: selectedEvent.error ? "#fca5a5" : "#e5e7eb" } },
            selectedEvent.error ? String(selectedEvent.error) : formatJson(resultPayload)
          )
        )
      );
    };

    return e(
      "div",
      { style: containerStyle },
      e(
        "div",
        { style: headerStyle },
        e(
          "div",
          { style: { display: "flex", alignItems: "center", gap: "10px" } },
          e("span", { style: { width: "10px", height: "10px", borderRadius: "50%", backgroundColor: guardOn ? "#10b981" : "#ef4444", display: "inline-block" } }),
          e("span", { style: { fontSize: "18px", fontWeight: 700 } }, "Phoenix Flight Recorder v2.0.0")
        ),
        e(
          "div",
          { style: { display: "flex", gap: "8px", flexWrap: "wrap" } },
          e("button", { type: "button", style: btnStyle, onClick: fetchAll }, "Sync WAL"),
          e(
            "button",
            {
              type: "button",
              disabled: wtState.running,
              style: Object.assign({}, btnStyle, { backgroundColor: "#2563eb", borderColor: "#3b82f6", color: "#ffffff" }),
              onClick: runWindTunnel
            },
            wtState.running ? "Running Crash-Replay Suite..." : "Run Crash-Replay Suite (ddmin)"
          )
        )
      ),
      e(
        "div",
        {
          style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            gap: "10px",
            marginBottom: "16px"
          }
        },
        makeCard("Protected Ops", stats.committed !== undefined ? stats.committed : 0, "#10b981"),
        makeCard("In-Flight WAL", stats.in_flight !== undefined ? stats.in_flight : 0, stats.in_flight > 0 ? "#f59e0b" : "#9ca3af"),
        makeCard("Dupes Prevented", stats.deduped !== undefined ? stats.deduped : 0, "#06b6d4"),
        makeCard("Recovered Landed", recoveredCount, recoveredCount > 0 ? "#f59e0b" : "#9ca3af"),
        makeCard("Guard Status", guardOn ? "ON" : "OFF", guardOn ? "#10b981" : "#ef4444")
      ),
      e(
        "div",
        {
          style: {
            display: "grid",
            gridTemplateColumns: "minmax(260px, 360px) 1fr",
            gap: "12px",
            marginBottom: "16px"
          }
        },
        e(
          "div",
          {
            style: {
              backgroundColor: "var(--ui-surface, #111827)",
              border: "1px solid var(--ui-border, #1f293d)",
              borderRadius: "8px",
              padding: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "8px"
            }
          },
          e("input", {
            type: "text",
            value: search,
            placeholder: "Filter tool, op_id, attempt_id...",
            onChange: function (ev) { setSearch(ev.target.value); },
            style: {
              width: "100%",
              boxSizing: "border-box",
              padding: "7px 10px",
              borderRadius: "6px",
              border: "1px solid #374151",
              backgroundColor: "#0b1220",
              color: "#f3f4f6",
              fontSize: "12px"
            }
          }),
          e(
            "div",
            { style: { display: "flex", flexWrap: "wrap", gap: "4px" } },
            STATUS_FILTERS.map(function (st) {
              var active = statusFilter === st;
              return e(
                "button",
                {
                  key: st,
                  type: "button",
                  onClick: function () { setStatusFilter(st); },
                  style: Object.assign({}, btnStyle, {
                    padding: "3px 8px",
                    fontSize: "11px",
                    backgroundColor: active ? "#2563eb" : "#1f293d",
                    color: active ? "#ffffff" : "#9ca3af"
                  })
                },
                st
              );
            })
          ),
          e(
            "div",
            { style: { maxHeight: "360px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "6px" } },
            filteredEvents.length === 0
              ? e("div", { style: { padding: "20px", textAlign: "center", color: "#9ca3af", fontSize: "12px" } }, "No matching WAL events")
              : filteredEvents.map(function (ev, idx) {
                  var key = ev.attempt_id || ev.op_id || String(idx);
                  var isSelected = selectedEvent && (selectedEvent.attempt_id || selectedEvent.op_id) === key;
                  var latency = getEventLatencyMs(ev);
                  return e(
                    "button",
                    {
                      key: key,
                      type: "button",
                      onClick: function () { setSelectedId(key); },
                      style: {
                        textAlign: "left",
                        width: "100%",
                        padding: "8px 10px",
                        borderRadius: "6px",
                        cursor: "pointer",
                        backgroundColor: isSelected ? "#1e293b" : "#0b1220",
                        border: "1px solid " + (isSelected ? "#3b82f6" : "#1f293d"),
                        color: "#f3f4f6"
                      }
                    },
                    e(
                      "div",
                      { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "6px" } },
                      e("span", { style: { fontFamily: "monospace", fontSize: "12px", fontWeight: 600 } }, ev.tool || ev.tool_name || "tool"),
                      e("span", { style: { fontSize: "10px", color: statusColor(ev.status), fontWeight: 700 } }, ev.status || "unknown")
                    ),
                    e(
                      "div",
                      { style: { display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#9ca3af", marginTop: "3px" } },
                      e("span", null, formatRelativeTime(ev.ts_done || ev.ts_intent || ev.timestamp)),
                      latency !== null ? e("span", null, latency + "ms") : null
                    )
                  );
                })
          )
        ),
        e(
          "div",
          {
            style: {
              backgroundColor: "var(--ui-surface, #111827)",
              border: "1px solid var(--ui-border, #1f293d)",
              borderRadius: "8px",
              minHeight: "360px"
            }
          },
          renderInspector()
        )
      ),
      e(
        "div",
        {
          style: {
            backgroundColor: "var(--ui-surface, #111827)",
            border: "1px solid var(--ui-border, #1f293d)",
            borderRadius: "8px",
            padding: "14px"
          }
        },
        e(
          "div",
          { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" } },
          e("strong", { style: { fontSize: "13px" } }, "Wind Tunnel Lab (Zeller ddmin)"),
          wtReport ? e("span", { style: { fontSize: "12px", fontWeight: 700, color: wtReport.passed ? "#10b981" : "#ef4444" } }, wtReport.passed ? "PASS" : "FAIL") : null
        ),
        wtState.error ? e("div", { style: { color: "#fca5a5", fontSize: "12px", marginBottom: "8px" } }, wtState.error) : null,
        wtChecks.length > 0
          ? e(
              "div",
              { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "8px" } },
              wtChecks.map(function (chk, idx) {
                return e(
                  "div",
                  {
                    key: chk.name || idx,
                    style: {
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 10px",
                      backgroundColor: "#0b1220",
                      border: "1px solid #1f293d",
                      borderRadius: "6px",
                      fontSize: "12px"
                    }
                  },
                  e("span", null, chk.name || chk.id || "Check " + (idx + 1)),
                  e("span", { style: { color: chk.passed ? "#10b981" : "#ef4444", fontWeight: 700 } }, chk.passed ? "PASS" : "FAIL")
                );
              })
            )
          : e("div", { style: { color: "#9ca3af", fontSize: "12px" } }, "Click \"Run Crash-Replay Suite (ddmin)\" to execute deterministic fault injection and trace minimization."),
        minimized
          ? e("pre", { style: { marginTop: "10px", padding: "10px", backgroundColor: "#0b1220", borderRadius: "6px", fontSize: "11px", whiteSpace: "pre-wrap" } }, formatJson(minimized))
          : null
      )
    );
  }

  REGISTRY.register("phoenix", PhoenixDashboardPanel);
})();
