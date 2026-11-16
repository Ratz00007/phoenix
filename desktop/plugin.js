import { useMemo, useState } from 'react';
import { Fragment, jsx, jsxs } from 'react/jsx-runtime';
import {
  Badge,
  Button,
  CopyButton,
  DecodeText,
  EmptyState,
  ErrorState,
  PANES_AREA,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  ScrollArea,
  SearchField,
  Separator,
  StatusDot,
  Tabs,
  TabsList,
  TabsTrigger,
  Tip,
  haptic,
  host,
  relativeTime,
  useMutation,
  useQuery,
  useQueryClient,
} from '@hermes/plugin-sdk';

const STATUS_FILTERS = ['all', 'intent', 'ok', 'deduped', 'recovered_landed', 'resumed', 'error'];

const STATUS_META = {
  ok: { badge: 'success', dot: 'good' },
  committed: { badge: 'success', dot: 'good' },
  deduped: { badge: 'default', dot: 'good' },
  recovered_landed: { badge: 'warn', dot: 'warn' },
  resumed: { badge: 'warn', dot: 'warn' },
  intent: { badge: 'warn', dot: 'warn' },
  error: { badge: 'destructive', dot: 'bad' },
};

function statusBadgeVariant(status) {
  const entry = STATUS_META[status];
  return entry ? entry.badge : 'muted';
}

function statusDotTone(status) {
  const entry = STATUS_META[status];
  return entry ? entry.dot : 'muted';
}

function toEpochMs(ts) {
  if (ts === null || ts === undefined || ts === '') {
    return null;
  }
  if (typeof ts === 'number') {
    if (!Number.isFinite(ts)) {
      return null;
    }
    return ts < 1e12 ? Math.round(ts * 1000) : Math.round(ts);
  }
  const parsed = Date.parse(String(ts));
  return Number.isNaN(parsed) ? null : parsed;
}

function formatRelTime(ts) {
  const ms = toEpochMs(ts);
  if (ms === null) {
    return null;
  }
  try {
    return relativeTime(ms);
  } catch {
    return String(ts);
  }
}

function formatJson(value) {
  if (value === undefined || value === null || value === '') {
    return '—';
  }
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function getEventTimestamp(ev) {
  return ev.ts_done || ev.ts_intent || ev.timestamp || ev.created_at || null;
}

function getEventLatencyMs(ev) {
  if (typeof ev.latency_ms === 'number') {
    return ev.latency_ms;
  }
  if (typeof ev.duration_ms === 'number') {
    return Math.max(0, Math.round(ev.duration_ms));
  }
  if (typeof ev.ts_done === 'number' && typeof ev.ts_intent === 'number') {
    return Math.max(0, Math.round((ev.ts_done - ev.ts_intent) * 1000));
  }
  return null;
}

function computeFpComparison(ev) {
  const pre = ev.pre_fp || ev.pre_fp_json || null;
  const post = ev.post_fp || ev.post_fp_json || null;
  if (!pre || !post) {
    return { verdict: 'PENDING', variant: 'warn', pre, post };
  }
  const preStr = typeof pre === 'string' ? pre : JSON.stringify(pre);
  const postStr = typeof post === 'string' ? post : JSON.stringify(post);
  if (preStr === postStr) {
    return { verdict: 'MATCH', variant: 'success', pre: preStr, post: postStr };
  }
  return { verdict: 'MUTATED', variant: 'destructive', pre: preStr, post: postStr };
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

function KpiCard({ label, value, color, dotTone, sublabel }) {
  return jsxs('div', {
    style: {
      background: 'var(--ui-surface-elevated, var(--ui-surface))',
      border: '1px solid var(--ui-border)',
      borderRadius: '10px',
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: '6px',
      minWidth: 0,
    },
    children: [
      jsxs('div', {
        style: {
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
        },
        children: [
          jsx('span', {
            style: {
              fontSize: '11px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--ui-text-muted)',
            },
            children: label,
          }),
          dotTone ? jsx(StatusDot, { tone: dotTone }) : null,
        ],
      }),
      jsx('div', {
        style: {
          fontSize: '22px',
          fontWeight: 700,
          lineHeight: 1.1,
          color: color || 'var(--ui-text)',
          fontVariantNumeric: 'tabular-nums',
        },
        children: jsx(DecodeText, { text: String(value) }),
      }),
      sublabel
        ? jsx('div', {
            style: {
              fontSize: '11px',
              color: 'var(--ui-text-muted)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            },
            children: sublabel,
          })
        : null,
    ],
  });
}

function ForensicInspector({ event }) {
  if (!event) {
    return jsx(EmptyState, {
      title: 'Select a WAL event',
      description: 'Inspect redacted args, idempotency keys, SHA-256 pre/post state fingerprints, and execution outcome.',
    });
  }

  const fp = computeFpComparison(event);
  const latency = getEventLatencyMs(event);
  const relTs = formatRelTime(getEventTimestamp(event));
  const attemptId = event.attempt_id || '—';
  const idempKey = event.idem_key || event.idempotency_key || event.op_id || '—';
  const toolName = event.tool || event.tool_name || 'unknown_tool';
  const argsPayload = event.args !== undefined ? event.args : event.args_json;
  const resultPayload = event.result !== undefined ? event.result : event.result_json;

  return jsxs('div', {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '14px',
      padding: '16px',
    },
    children: [
      jsxs('div', {
        style: {
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          flexWrap: 'wrap',
        },
        children: [
          jsxs('div', {
            style: { display: 'flex', alignItems: 'center', gap: '8px' },
            children: [
              jsx(StatusDot, { tone: statusDotTone(event.status) }),
              jsx('span', {
                style: {
                  fontSize: '15px',
                  fontWeight: 700,
                  color: 'var(--ui-text)',
                  fontFamily: 'var(--ui-font-mono, monospace)',
                },
                children: toolName,
              }),
              jsx(Badge, {
                variant: statusBadgeVariant(event.status),
                children: event.status || 'unknown',
              }),
            ],
          }),
          jsxs('div', {
            style: {
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '12px',
              color: 'var(--ui-text-muted)',
            },
            children: [
              latency !== null ? jsx('span', { children: `${latency}ms` }) : null,
              relTs ? jsx('span', { children: relTs }) : null,
            ],
          }),
        ],
      }),
      jsx(Separator, {}),
      jsxs('div', {
        style: {
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '10px',
        },
        children: [
          jsxs('div', {
            style: {
              background: 'var(--ui-surface)',
              border: '1px solid var(--ui-border)',
              borderRadius: '8px',
              padding: '10px 12px',
            },
            children: [
              jsxs('div', {
                style: {
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '4px',
                },
                children: [
                  jsx('span', {
                    style: { fontSize: '11px', color: 'var(--ui-text-muted)', fontWeight: 600 },
                    children: 'ATTEMPT ID',
                  }),
                  jsx(CopyButton, { text: attemptId, appearance: 'inline', buttonSize: 'xs' }),
                ],
              }),
              jsx('div', {
                style: {
                  fontSize: '12px',
                  fontFamily: 'var(--ui-font-mono, monospace)',
                  color: 'var(--ui-text)',
                  wordBreak: 'break-all',
                },
                children: attemptId,
              }),
            ],
          }),
          jsxs('div', {
            style: {
              background: 'var(--ui-surface)',
              border: '1px solid var(--ui-border)',
              borderRadius: '8px',
              padding: '10px 12px',
            },
            children: [
              jsxs('div', {
                style: {
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '4px',
                },
                children: [
                  jsx('span', {
                    style: { fontSize: '11px', color: 'var(--ui-text-muted)', fontWeight: 600 },
                    children: 'OP ID / IDEMPOTENCY KEY',
                  }),
                  jsx(CopyButton, { text: idempKey, appearance: 'inline', buttonSize: 'xs' }),
                ],
              }),
              jsx('div', {
                style: {
                  fontSize: '12px',
                  fontFamily: 'var(--ui-font-mono, monospace)',
                  color: 'var(--ui-text)',
                  wordBreak: 'break-all',
                },
                children: idempKey,
              }),
            ],
          }),
        ],
      }),
      jsxs('div', {
        style: {
          background: 'var(--ui-surface)',
          border: '1px solid var(--ui-border)',
          borderRadius: '8px',
          padding: '12px',
        },
        children: [
          jsxs('div', {
            style: {
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '8px',
            },
            children: [
              jsx('span', {
                style: { fontSize: '12px', fontWeight: 600, color: 'var(--ui-text)' },
                children: 'SHA-256 State Fingerprint Diff (pre_fp vs post_fp)',
              }),
              jsx(Badge, { variant: fp.variant, children: fp.verdict }),
            ],
          }),
          jsxs('div', {
            style: {
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '8px',
              fontSize: '11px',
              fontFamily: 'var(--ui-font-mono, monospace)',
            },
            children: [
              jsxs('div', {
                style: {
                  padding: '8px',
                  borderRadius: '6px',
                  background: 'var(--ui-surface-elevated, var(--ui-bg))',
                  border: '1px solid var(--ui-border)',
                  overflowX: 'auto',
                },
                children: [
                  jsx('div', {
                    style: { color: 'var(--ui-text-muted)', marginBottom: '4px' },
                    children: 'pre_fp',
                  }),
                  jsx('div', {
                    style: { color: 'var(--ui-text)', wordBreak: 'break-all' },
                    children: fp.pre ? formatJson(fp.pre) : '—',
                  }),
                ],
              }),
              jsxs('div', {
                style: {
                  padding: '8px',
                  borderRadius: '6px',
                  background: 'var(--ui-surface-elevated, var(--ui-bg))',
                  border: '1px solid var(--ui-border)',
                  overflowX: 'auto',
                },
                children: [
                  jsx('div', {
                    style: { color: 'var(--ui-text-muted)', marginBottom: '4px' },
                    children: 'post_fp',
                  }),
                  jsx('div', {
                    style: { color: 'var(--ui-text)', wordBreak: 'break-all' },
                    children: fp.post ? formatJson(fp.post) : '—',
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
      jsxs('div', {
        style: {
          background: 'var(--ui-surface)',
          border: '1px solid var(--ui-border)',
          borderRadius: '8px',
          padding: '12px',
        },
        children: [
          jsx('div', {
            style: { fontSize: '12px', fontWeight: 600, color: 'var(--ui-text)', marginBottom: '6px' },
            children: 'Redacted Arguments',
          }),
          jsx('pre', {
            style: {
              margin: 0,
              fontSize: '12px',
              lineHeight: 1.45,
              fontFamily: 'var(--ui-font-mono, monospace)',
              color: 'var(--ui-text)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            },
            children: formatJson(argsPayload),
          }),
        ],
      }),
      jsxs('div', {
        style: {
          background: 'var(--ui-surface)',
          border: `1px solid ${event.error ? 'var(--ui-danger, var(--ui-border))' : 'var(--ui-border)'}`,
          borderRadius: '8px',
          padding: '12px',
        },
        children: [
          jsx('div', {
            style: { fontSize: '12px', fontWeight: 600, color: 'var(--ui-text)', marginBottom: '6px' },
            children: event.error ? 'Error Outcome' : 'Result Outcome',
          }),
          jsx('pre', {
            style: {
              margin: 0,
              fontSize: '12px',
              lineHeight: 1.45,
              fontFamily: 'var(--ui-font-mono, monospace)',
              color: event.error ? 'var(--ui-danger, var(--ui-text))' : 'var(--ui-text)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            },
            children: event.error ? String(event.error) : formatJson(resultPayload),
          }),
        ],
      }),
    ],
  });
}

function WindTunnelLab({ ctx, initialReport }) {
  const queryClient = useQueryClient();
  const windTunnelMutation = useMutation({
    mutationFn: () => ctx.rest('/windtunnel', { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['phoenix', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['phoenix', 'timeline'] });
    },
  });

  const rawReport = windTunnelMutation.data || initialReport || null;
  const report = rawReport && rawReport.report ? rawReport.report : rawReport;
  const checks = report && Array.isArray(report.checks) ? report.checks : [];
  const minimized =
    (report && (report.ddmin || report.minimized_trace || report.ddmin_trace || report.counterexample)) || null;

  return jsxs('div', {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '14px',
      padding: '4px 0',
    },
    children: [
      jsxs('div', {
        style: {
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          flexWrap: 'wrap',
          background: 'var(--ui-surface-elevated, var(--ui-surface))',
          border: '1px solid var(--ui-border)',
          borderRadius: '10px',
          padding: '14px 16px',
        },
        children: [
          jsxs('div', {
            style: { display: 'flex', flexDirection: 'column', gap: '4px' },
            children: [
              jsx('div', {
                style: { fontSize: '14px', fontWeight: 700, color: 'var(--ui-text)' },
                children: 'Deterministic Fault-Injection Wind Tunnel (Zeller ddmin)',
              }),
              jsx('div', {
                style: { fontSize: '12px', color: 'var(--ui-text-muted)' },
                children: 'Replays crash, timeout-after-commit, and 429 retry faults against the real SQLite WAL guard.',
              }),
            ],
          }),
          jsx(Button, {
            variant: 'default',
            disabled: windTunnelMutation.isPending,
            onClick: () => {
              haptic('tap');
              windTunnelMutation.mutate();
            },
            children: windTunnelMutation.isPending
              ? 'Running Crash-Replay Suite...'
              : 'Run Crash-Replay Suite (ddmin)',
          }),
        ],
      }),
      windTunnelMutation.isError
        ? jsx(ErrorState, {
            title: 'Wind Tunnel run failed',
            description: String(
              windTunnelMutation.error && windTunnelMutation.error.message
                ? windTunnelMutation.error.message
                : windTunnelMutation.error
            ),
          })
        : null,
      checks.length > 0
        ? jsxs('div', {
            style: {
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            },
            children: [
              jsxs('div', {
                style: {
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                },
                children: [
                  jsx('span', {
                    style: { fontSize: '13px', fontWeight: 600, color: 'var(--ui-text)' },
                    children: 'Verification Checks',
                  }),
                  jsx(Badge, {
                    variant: report && report.passed ? 'success' : 'destructive',
                    children: report && report.passed ? 'ALL CHECKS PASS' : 'CHECK FAILED',
                  }),
                ],
              }),
              jsx('div', {
                style: {
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: '8px',
                },
                children: checks.map((chk, idx) =>
                  jsxs(
                    'div',
                    {
                      style: {
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '10px',
                        padding: '10px 12px',
                        background: 'var(--ui-surface)',
                        border: '1px solid var(--ui-border)',
                        borderRadius: '8px',
                      },
                      children: [
                        jsxs('div', {
                          style: { display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 },
                          children: [
                            jsx(StatusDot, { tone: chk.passed ? 'good' : 'bad' }),
                            jsx('span', {
                              style: {
                                fontSize: '12px',
                                fontWeight: 500,
                                color: 'var(--ui-text)',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              },
                              children: chk.name || chk.id || `Check ${idx + 1}`,
                            }),
                          ],
                        }),
                        jsx(Badge, {
                          variant: chk.passed ? 'success' : 'destructive',
                          children: chk.passed ? 'PASS' : 'FAIL',
                        }),
                      ],
                    },
                    chk.name || idx
                  )
                ),
              }),
            ],
          })
        : jsx(EmptyState, {
            title: 'No Wind Tunnel checks loaded yet',
            description: 'Click "Run Crash-Replay Suite (ddmin)" to execute deterministic fault injection and trace minimization.',
          }),
      minimized
        ? jsxs('div', {
            style: {
              background: 'var(--ui-surface)',
              border: '1px solid var(--ui-border)',
              borderRadius: '8px',
              padding: '12px',
            },
            children: [
              jsx('div', {
                style: { fontSize: '12px', fontWeight: 600, color: 'var(--ui-text)', marginBottom: '6px' },
                children: 'Minimized Failing Sequence (ddmin)',
              }),
              jsx('pre', {
                style: {
                  margin: 0,
                  fontSize: '12px',
                  fontFamily: 'var(--ui-font-mono, monospace)',
                  color: 'var(--ui-text)',
                  whiteSpace: 'pre-wrap',
                },
                children: formatJson(minimized),
              }),
            ],
          })
        : null,
    ],
  });
}

function createPhoenixFlightRecorder(ctx) {
  return function PhoenixFlightRecorderPage() {
    const [activeTab, setActiveTab] = useState('recorder');
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [selectedId, setSelectedId] = useState(null);

    const statusQuery = useQuery({
      queryKey: ['phoenix', 'status'],
      queryFn: () => ctx.rest('/status'),
      refetchInterval: 4000,
    });

    const timelineQuery = useQuery({
      queryKey: ['phoenix', 'timeline'],
      queryFn: async () => {
        try {
          return await ctx.rest('/timeline');
        } catch {
          return null;
        }
      },
      refetchInterval: 4000,
    });

    const statusData = statusQuery.data || {};
    const stats = statusData.stats || statusData;
    const guardOn = statusData.guard_enabled !== undefined ? Boolean(statusData.guard_enabled) : true;
    const events = useMemo(
      () => normalizeEvents(timelineQuery.data, statusData),
      [timelineQuery.data, statusData]
    );

    const recoveredCount = useMemo(() => {
      if (typeof statusData.recovered_landed === 'number') {
        return statusData.recovered_landed;
      }
      if (typeof stats.recovered_landed === 'number') {
        return stats.recovered_landed;
      }
      return events.filter((ev) => ev.status === 'recovered_landed').length;
    }, [statusData.recovered_landed, stats.recovered_landed, events]);

    const filteredEvents = useMemo(() => {
      const q = search.trim().toLowerCase();
      return events.filter((ev) => {
        if (statusFilter !== 'all' && ev.status !== statusFilter) {
          return false;
        }
        if (!q) {
          return true;
        }
        const hay = [
          ev.tool,
          ev.tool_name,
          ev.op_id,
          ev.attempt_id,
          ev.idem_key,
          ev.idempotency_key,
          ev.status,
          typeof ev.args === 'string' ? ev.args : JSON.stringify(ev.args || ''),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return hay.includes(q);
      });
    }, [events, statusFilter, search]);

    const selectedEvent = useMemo(() => {
      if (filteredEvents.length === 0) {
        return null;
      }
      if (selectedId) {
        const match = filteredEvents.find(
          (ev) => (ev.attempt_id || ev.op_id) === selectedId
        );
        if (match) {
          return match;
        }
      }
      return filteredEvents[0];
    }, [filteredEvents, selectedId]);

    if (statusQuery.isError && !statusQuery.data) {
      return jsx(ErrorState, {
        title: 'Unable to reach Phoenix Flight Recorder',
        description: String(
          statusQuery.error && statusQuery.error.message ? statusQuery.error.message : statusQuery.error
        ),
      });
    }

    const recorderContent = jsxs('div', {
      style: {
        display: 'grid',
        gridTemplateColumns: 'minmax(280px, 380px) 1fr',
        gap: '12px',
        marginTop: '12px',
        minHeight: '420px',
      },
      children: [
        jsxs('div', {
          style: {
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            background: 'var(--ui-surface-elevated, var(--ui-surface))',
            border: '1px solid var(--ui-border)',
            borderRadius: '10px',
            padding: '12px',
            minHeight: 0,
          },
          children: [
            jsx(SearchField, {
              value: search,
              onChange: (val) => setSearch(typeof val === 'string' ? val : val && val.target ? val.target.value : ''),
              placeholder: 'Filter tool, op_id, attempt_id...',
            }),
            jsx('div', {
              style: {
                display: 'flex',
                flexWrap: 'wrap',
                gap: '6px',
              },
              children: STATUS_FILTERS.map((st) =>
                jsx(
                  Button,
                  {
                    size: 'xs',
                    variant: statusFilter === st ? 'default' : 'ghost',
                    onClick: () => {
                      haptic('selection');
                      setStatusFilter(st);
                    },
                    children: st,
                  },
                  st
                )
              ),
            }),
            jsx(Separator, {}),
            jsx(ScrollArea, {
              style: { maxHeight: '420px' },
              children:
                filteredEvents.length === 0
                  ? jsx(EmptyState, {
                      title: 'No WAL events',
                      description: 'Tool executions guarded by Phoenix will stream here.',
                    })
                  : jsx('div', {
                      style: { display: 'flex', flexDirection: 'column', gap: '6px' },
                      children: filteredEvents.map((ev, idx) => {
                        const key = ev.attempt_id || ev.op_id || String(idx);
                        const isSelected = selectedEvent && (selectedEvent.attempt_id || selectedEvent.op_id) === key;
                        const latency = getEventLatencyMs(ev);
                        const relTs = formatRelTime(getEventTimestamp(ev));
                        return jsxs(
                          'button',
                          {
                            type: 'button',
                            onClick: () => {
                              haptic('selection');
                              setSelectedId(key);
                            },
                            style: {
                              textAlign: 'left',
                              width: '100%',
                              padding: '10px',
                              borderRadius: '8px',
                              cursor: 'pointer',
                              background: isSelected
                                ? 'var(--ui-surface-active, var(--ui-surface))'
                                : 'transparent',
                              border: `1px solid ${isSelected ? 'var(--ui-accent, var(--ui-border))' : 'var(--ui-border)'}`,
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '4px',
                            },
                            children: [
                              jsxs('div', {
                                style: {
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  gap: '8px',
                                },
                                children: [
                                  jsxs('div', {
                                    style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 },
                                    children: [
                                      jsx(StatusDot, { tone: statusDotTone(ev.status) }),
                                      jsx('span', {
                                        style: {
                                          fontSize: '12px',
                                          fontWeight: 600,
                                          color: 'var(--ui-text)',
                                          fontFamily: 'var(--ui-font-mono, monospace)',
                                          overflow: 'hidden',
                                          textOverflow: 'ellipsis',
                                          whiteSpace: 'nowrap',
                                        },
                                        children: ev.tool || ev.tool_name || 'tool',
                                      }),
                                    ],
                                  }),
                                  jsx(Badge, {
                                    variant: statusBadgeVariant(ev.status),
                                    children: ev.status || 'unknown',
                                  }),
                                ],
                              }),
                              jsxs('div', {
                                style: {
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  fontSize: '11px',
                                  color: 'var(--ui-text-muted)',
                                },
                                children: [
                                  jsx('span', { children: relTs || 'just now' }),
                                  latency !== null ? jsx('span', { children: `${latency}ms` }) : null,
                                ],
                              }),
                            ],
                          },
                          key
                        );
                      }),
                    }),
            }),
          ],
        }),
        jsx('div', {
          style: {
            background: 'var(--ui-surface-elevated, var(--ui-surface))',
            border: '1px solid var(--ui-border)',
            borderRadius: '10px',
            minHeight: 0,
            overflow: 'auto',
          },
          children: jsx(ForensicInspector, { event: selectedEvent }),
        }),
      ],
    });

    const windTunnelContent = jsx('div', {
      style: { marginTop: '12px' },
      children: jsx(WindTunnelLab, {
        ctx,
        initialReport: statusData.windtunnel_report || null,
      }),
    });

    return jsxs('div', {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        padding: '20px',
        height: '100%',
        boxSizing: 'border-box',
        color: 'var(--ui-text)',
      },
      children: [
        jsxs('div', {
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          },
          children: [
            jsxs('div', {
              style: { display: 'flex', alignItems: 'center', gap: '10px' },
              children: [
                jsx(StatusDot, { tone: guardOn ? 'good' : 'bad' }),
                jsx('h1', {
                  style: { margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--ui-text)' },
                  children: 'Phoenix Flight Recorder',
                }),
                jsx(Badge, { variant: guardOn ? 'success' : 'destructive', children: guardOn ? 'GUARD ON' : 'GUARD OFF' }),
              ],
            }),
            jsx(Tip, {
              label: 'Refresh WAL state and timeline',
              children: jsx(Button, {
                variant: 'secondary',
                size: 'sm',
                onClick: () => {
                  haptic('tap');
                  statusQuery.refetch();
                  timelineQuery.refetch();
                },
                children: statusQuery.isFetching ? 'Syncing...' : 'Sync WAL',
              }),
            }),
          ],
        }),
        jsxs('div', {
          style: {
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '10px',
          },
          children: [
            jsx(KpiCard, {
              label: 'Protected Ops',
              value: stats.committed !== undefined ? stats.committed : 0,
              color: 'var(--ui-success, var(--ui-text))',
              dotTone: 'good',
              sublabel: `Total WAL rows: ${stats.total !== undefined ? stats.total : 0}`,
            }),
            jsx(KpiCard, {
              label: 'In-Flight WAL',
              value: stats.in_flight !== undefined ? stats.in_flight : 0,
              color: (stats.in_flight || 0) > 0 ? 'var(--ui-warning, var(--ui-text))' : 'var(--ui-text)',
              dotTone: (stats.in_flight || 0) > 0 ? 'warn' : 'muted',
              sublabel: 'Uncommitted intent rows',
            }),
            jsx(KpiCard, {
              label: 'Dupes Prevented',
              value: stats.deduped !== undefined ? stats.deduped : 0,
              color: 'var(--ui-accent, var(--ui-text))',
              dotTone: 'good',
              sublabel: 'Idempotency guard hits',
            }),
            jsx(KpiCard, {
              label: 'Recovered Landed',
              value: recoveredCount,
              color: 'var(--ui-warning, var(--ui-text))',
              dotTone: recoveredCount > 0 ? 'warn' : 'muted',
              sublabel: 'Post-crash verified',
            }),
            jsx(KpiCard, {
              label: 'Guard Status',
              value: guardOn ? 'ON' : 'OFF',
              color: guardOn ? 'var(--ui-success, var(--ui-text))' : 'var(--ui-danger, var(--ui-text))',
              dotTone: guardOn ? 'good' : 'bad',
              sublabel: statusData.windtunnel_verdict || 'Wind Tunnel ready',
            }),
          ],
        }),
        jsxs(Tabs, {
          value: activeTab,
          onValueChange: (val) => {
            haptic('selection');
            setActiveTab(val);
          },
          children: [
            jsxs(TabsList, {
              children: [
                jsx(TabsTrigger, { value: 'recorder', children: 'Flight Recorder' }),
                jsx(TabsTrigger, { value: 'windtunnel', children: 'Wind Tunnel Lab' }),
              ],
            }),
            activeTab === 'recorder' ? recorderContent : windTunnelContent,
          ],
        }),
      ],
    });
  };
}

function createPhoenixDrawerPane(ctx) {
  return function PhoenixDrawerPane() {
    const statusQuery = useQuery({
      queryKey: ['phoenix', 'status'],
      queryFn: () => ctx.rest('/status'),
      refetchInterval: 4000,
    });
    const timelineQuery = useQuery({
      queryKey: ['phoenix', 'timeline'],
      queryFn: async () => {
        try {
          return await ctx.rest('/timeline');
        } catch {
          return null;
        }
      },
      refetchInterval: 4000,
    });

    const data = statusQuery.data || {};
    const stats = data.stats || data;
    const guardOn = data.guard_enabled !== undefined ? Boolean(data.guard_enabled) : true;
    const inFlight = stats.in_flight !== undefined ? stats.in_flight : 0;
    const latest = normalizeEvents(timelineQuery.data, data).slice(0, 10);

    return jsxs('div', {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '12px',
        color: 'var(--ui-text)',
      },
      children: [
        jsxs('div', {
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
          },
          children: [
            jsxs('div', {
              style: { display: 'flex', alignItems: 'center', gap: '6px' },
              children: [
                jsx(StatusDot, { tone: guardOn ? 'good' : 'bad' }),
                jsx('span', {
                  style: { fontSize: '13px', fontWeight: 700 },
                  children: guardOn ? 'Guard ON' : 'Guard OFF',
                }),
              ],
            }),
            jsx(Badge, {
              variant: inFlight > 0 ? 'warn' : 'muted',
              children: `${inFlight} in-flight`,
            }),
          ],
        }),
        jsx(Separator, {}),
        jsx(ScrollArea, {
          style: { maxHeight: '320px' },
          children:
            latest.length === 0
              ? jsx(EmptyState, {
                  title: 'No recent events',
                  description: 'Latest 10 WAL operations appear here.',
                })
              : jsx('div', {
                  style: { display: 'flex', flexDirection: 'column', gap: '6px' },
                  children: latest.map((ev, idx) => {
                    const relTs = formatRelTime(getEventTimestamp(ev));
                    return jsxs(
                      'div',
                      {
                        style: {
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '8px',
                          padding: '6px 8px',
                          borderRadius: '6px',
                          background: 'var(--ui-surface)',
                          border: '1px solid var(--ui-border)',
                        },
                        children: [
                          jsxs('div', {
                            style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 },
                            children: [
                              jsx(StatusDot, { tone: statusDotTone(ev.status) }),
                              jsx('span', {
                                style: {
                                  fontSize: '12px',
                                  fontFamily: 'var(--ui-font-mono, monospace)',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                },
                                children: ev.tool || ev.tool_name || 'tool',
                              }),
                            ],
                          }),
                          jsxs('div', {
                            style: { display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 },
                            children: [
                              relTs
                                ? jsx('span', {
                                    style: { fontSize: '10px', color: 'var(--ui-text-muted)' },
                                    children: relTs,
                                  })
                                : null,
                              jsx(Badge, {
                                variant: statusBadgeVariant(ev.status),
                                children: ev.status || 'unknown',
                              }),
                            ],
                          }),
                        ],
                      },
                      ev.attempt_id || ev.op_id || idx
                    );
                  }),
                }),
        }),
      ],
    });
  };
}

function createPhoenixStatusPill(ctx) {
  return function PhoenixStatusPill() {
    const statusQuery = useQuery({
      queryKey: ['phoenix', 'status'],
      queryFn: () => ctx.rest('/status'),
      refetchInterval: 5000,
    });

    const data = statusQuery.data || {};
    const stats = data.stats || data;
    const guardOn = data.guard_enabled !== undefined ? Boolean(data.guard_enabled) : true;
    const inFlight = stats.in_flight !== undefined ? stats.in_flight : 0;

    return jsx(Tip, {
      label: 'Open Phoenix Flight Recorder',
      children: jsxs('button', {
        type: 'button',
        onClick: () => {
          haptic('tap');
          host.navigate('/phoenix');
        },
        style: {
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          background: 'transparent',
          border: 'none',
          color: 'var(--ui-text-muted)',
          fontSize: '12px',
          cursor: 'pointer',
          padding: '2px 6px',
        },
        children: [
          jsx(StatusDot, { tone: guardOn ? 'good' : 'bad' }),
          jsx('span', {
            children: `Phoenix · Guard ${guardOn ? 'ON' : 'OFF'} · ${inFlight} in-flight`,
          }),
        ],
      }),
    });
  };
}

export default {
  id: 'phoenix',
  name: 'Phoenix Flight Recorder',
  description: 'Crash-proof SQLite WAL ledger, SHA-256 pre/post state fingerprinting, and Zeller ddmin wind tunnel.',
  register(ctx) {
    const FlightRecorderPage = createPhoenixFlightRecorder(ctx);
    const DrawerPane = createPhoenixDrawerPane(ctx);
    const StatusPill = createPhoenixStatusPill(ctx);

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/phoenix' },
        render: () => jsx(FlightRecorderPage, {}),
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 55,
        data: { path: '/phoenix', label: 'Phoenix', codicon: 'flame' },
      },
      {
        id: 'pane',
        area: PANES_AREA,
        title: 'Flight Recorder',
        data: { placement: 'right', width: '320px' },
        render: () => jsx(DrawerPane, {}),
      },
      {
        id: 'status',
        area: STATUSBAR_AREAS.right,
        order: 85,
        render: () => jsx(StatusPill, {}),
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'phoenix.open',
          label: 'Phoenix: Open Flight Recorder',
          keywords: ['phoenix', 'wal', 'flight recorder', 'windtunnel', 'recovery'],
          run: () => {
            haptic('tap');
            host.navigate('/phoenix');
          },
        },
      },
    ]);
  },
};
