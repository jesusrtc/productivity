/** Alert lifecycle statuses */
export type AlertStatus = 'new' | 'investigating' | 'resolved' | 'dismissed'

/** Alert severity levels */
export type AlertSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info'

/** Where the alert came from */
export type AlertSource = 'inresponse' | 'iris' | 'manual' | 'playbook' | 'external'

/** An extracted IOC from an alert */
export interface AlertIOC {
  type: 'ip' | 'domain' | 'member_id' | 'email' | 'device_hash' | 'user_agent' | 'other'
  value: string
}

/** Core alert entity */
export interface Alert {
  id: string
  /** External ID from InResponse or IRIS */
  external_id?: string
  title: string
  description: string
  status: AlertStatus
  severity: AlertSeverity
  source: AlertSource

  /** Alert type/category (maps to investigation-router categories) */
  alert_type: string
  /** Assignee (LinkedIn username) */
  assignee?: string

  created_at: string
  updated_at: string
  resolved_at?: string

  /** Linked investigation session IDs */
  session_ids: string[]
  /** Related alert IDs (same IOCs, same incident, etc.) */
  related_alert_ids: string[]
  /** Extracted IOCs for cross-alert correlation */
  iocs: AlertIOC[]

  /** Suggested playbook ID based on alert type */
  suggested_playbook_id?: string
  /** InResponse incident ID if linked */
  incident_id?: string

  /** Arbitrary metadata from the source system */
  metadata: Record<string, unknown>
  /** Tags for filtering */
  tags: string[]
}

/** Lightweight alert summary for list views */
export interface AlertSummary {
  id: string
  external_id?: string
  title: string
  status: AlertStatus
  severity: AlertSeverity
  source: AlertSource
  alert_type: string
  assignee?: string
  created_at: string
  updated_at: string
  session_count: number
  ioc_count: number
  related_count: number
  tags: string[]
}

/** Filters for the alert queue */
export interface AlertFilters {
  status?: AlertStatus[]
  severity?: AlertSeverity[]
  source?: AlertSource[]
  alert_type?: string
  assignee?: string
  search?: string
  date_from?: string
  date_to?: string
}

/** Create a new empty alert */
export function createAlert(overrides: Partial<Alert> & { id: string; title: string }): Alert {
  return {
    description: '',
    status: 'new',
    severity: 'medium',
    source: 'manual',
    alert_type: '',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    session_ids: [],
    related_alert_ids: [],
    iocs: [],
    metadata: {},
    tags: [],
    ...overrides,
  }
}
