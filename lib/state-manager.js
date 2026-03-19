/**
 * State Manager
 * Persists daemon state across restarts
 */

import fs from 'fs/promises';
import path from 'path';

export class StateManager {
  constructor(agentName, workspaceRoot) {
    this.agentName = agentName;
    this.statePath = path.join(workspaceRoot, 'services/agent-tick/state', `${agentName}.json`);
  }

  async load() {
    try {
      const data = await fs.readFile(this.statePath, 'utf-8');
      return JSON.parse(data);
    } catch {
      return this.getDefaultState();
    }
  }

  async save(state) {
    await fs.writeFile(this.statePath, JSON.stringify(state, null, 2));
  }

  async updateLastPublished(channel) {
    const state = await this.load();
    if (!state.lastPublished) state.lastPublished = {};
    state.lastPublished[channel] = Date.now();
    await this.save(state);
  }

  async addPendingEvent(event) {
    const state = await this.load();
    if (!state.pendingEvents) state.pendingEvents = [];
    state.pendingEvents.push(event);

    // Keep only last 30 days
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    state.pendingEvents = state.pendingEvents.filter(e => e.timestamp > cutoff);

    await this.save(state);
  }

  getDefaultState() {
    return {
      version: '1.0.0',
      lastTick: Date.now(),
      daemonState: 'idle',
      lastPublished: {},
      pendingEvents: [],
      pendingDrafts: {},
      publishedThisWeek: {
        blog: 0,
        x_thread: 0,
        weekStarting: this.getWeekStart()
      },
      eventHistory: []
    };
  }

  getWeekStart() {
    const now = new Date();
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1); // Monday
    const monday = new Date(now.setDate(diff));
    return monday.toISOString().split('T')[0];
  }
}
