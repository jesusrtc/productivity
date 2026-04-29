/**
 * Direct MCP client for the Captain server.
 *
 * Spawns `captain start` (FastMCP STDIO) and speaks JSON-RPC 2.0 over
 * newline-delimited JSON — Captain's actual transport format.
 *
 * Captain exposes 3 meta-tools: get_tools_for_tags, get_tool_info, exec_tool.
 * Real tools like execute_trino_query are called via exec_tool.
 *
 * This lets the Juniper server call Captain tools without routing through
 * a `claude -p` subprocess, eliminating the MCP-still-connecting race.
 */

import { spawn, type ChildProcess } from 'child_process'

interface JsonRpcRequest {
  jsonrpc: '2.0'
  id: number
  method: string
  params?: Record<string, unknown>
}

interface JsonRpcResponse {
  jsonrpc: '2.0'
  id?: number
  method?: string
  result?: unknown
  error?: { code: number; message: string; data?: unknown }
}

type PendingRequest = {
  resolve: (value: JsonRpcResponse) => void
  reject: (err: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export class CaptainClient {
  private proc: ChildProcess | null = null
  private nextId = 1
  private pending = new Map<number, PendingRequest>()
  private buffer = ''
  private initialized = false
  private initPromise: Promise<void> | null = null
  private readonly timeout: number

  /** @param timeoutMs Per-request timeout (default 120 s) */
  constructor(timeoutMs = 120_000) {
    this.timeout = timeoutMs
  }

  /** Ensure the Captain process is running and initialized. */
  async connect(): Promise<void> {
    if (this.initialized && this.proc && !this.proc.killed) return
    if (this.initPromise) return this.initPromise

    this.initPromise = this._start().catch((err) => {
      this.initPromise = null
      this.initialized = false
      throw err
    })
    await this.initPromise
  }

  private async _start(): Promise<void> {
    this.proc = spawn('captain', ['start'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
    })

    this.proc.stdout!.on('data', (chunk: Buffer) => this._onData(chunk))
    this.proc.stderr!.on('data', () => {})  // suppress stderr noise
    this.proc.on('close', () => {
      this.initialized = false
      this.initPromise = null
      for (const [id, p] of this.pending) {
        clearTimeout(p.timer)
        p.reject(new Error('Captain process exited'))
        this.pending.delete(id)
      }
    })

    // MCP initialize handshake
    const initResp = await this._send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: { name: 'juniper-server', version: '1.0.0' },
      },
    })

    if (initResp.error) {
      throw new Error(`MCP init failed: ${initResp.error.message}`)
    }

    // Send initialized notification
    this._write({ jsonrpc: '2.0', method: 'notifications/initialized' })
    this.initialized = true
  }

  /**
   * Call a Captain tool by name via the exec_tool wrapper.
   * Returns the tool result text.
   */
  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.connect()

    const resp = await this._send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'tools/call',
      params: {
        name: 'exec_tool',
        arguments: { tool_name: name, args },
      },
    })

    if (resp.error) {
      throw new Error(`Tool ${name} failed: ${resp.error.message}`)
    }

    const result = resp.result as any

    // Check isError flag from Captain
    if (result?.isError) {
      const errText = result?.content?.map((c: any) => c.text).join('\n') || 'Unknown error'
      throw new Error(`Tool ${name} error: ${errText}`)
    }

    // Extract text from MCP content blocks
    if (result?.content && Array.isArray(result.content)) {
      return result.content
        .filter((c: any) => c.type === 'text')
        .map((c: any) => c.text)
        .join('\n')
    }
    return JSON.stringify(result)
  }

  /** Shut down the Captain process. */
  close(): void {
    if (this.proc && !this.proc.killed) {
      try { this.proc.kill('SIGTERM') } catch {}
    }
    this.proc = null
    this.initialized = false
    this.initPromise = null
  }

  // ── Newline-delimited JSON transport ──

  private _send(req: JsonRpcRequest): Promise<JsonRpcResponse> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(req.id)
        reject(new Error(`Captain request ${req.method} timed out after ${this.timeout}ms`))
      }, this.timeout)

      this.pending.set(req.id, { resolve, reject, timer })
      this._write(req)
    })
  }

  private _write(msg: Record<string, unknown>): void {
    if (!this.proc?.stdin?.writable) return
    this.proc.stdin.write(JSON.stringify(msg) + '\n')
  }

  private _onData(chunk: Buffer): void {
    this.buffer += chunk.toString()

    // Parse newline-delimited JSON
    const lines = this.buffer.split('\n')
    this.buffer = lines.pop() || '' // keep incomplete last line

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const msg = JSON.parse(line) as JsonRpcResponse
        // Only resolve requests (messages with an id matching a pending request)
        if (msg.id != null && this.pending.has(msg.id)) {
          const p = this.pending.get(msg.id)!
          clearTimeout(p.timer)
          this.pending.delete(msg.id)
          p.resolve(msg)
        }
        // Ignore notifications (no id) — e.g. log messages, errors
      } catch {
        // Skip unparseable lines
      }
    }
  }
}

/** Singleton instance — reused across all queries in this server. */
let _instance: CaptainClient | null = null

export function getCaptainClient(): CaptainClient {
  if (!_instance) _instance = new CaptainClient()
  return _instance
}
