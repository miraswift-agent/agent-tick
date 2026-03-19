#!/usr/bin/env node
/**
 * Agent Tick - Reusable Daemon for AI Agent Autonomy
 * 
 * Usage: node daemon.js --agent=<name>
 * Example: node daemon.js --agent=mira
 */

import { EventEmitter } from 'events';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { AdaptiveScheduler } from './lib/adaptive-scheduler.js';
import { EventDetector } from './lib/event-detector.js';
import { StateManager } from './lib/state-manager.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

class AgentTickDaemon extends EventEmitter {
  constructor(config, agentName) {
    super();
    this.agentName = agentName;
    this.config = config;
    this.scheduler = new AdaptiveScheduler(config);
    this.detector = new EventDetector(config, agentName);
    this.stateManager = new StateManager(agentName, config.workspaceRoot);
    this.tickTimer = null;
    this.tickCount = 0;
  }

  async start() {
    console.log(`[AgentTick:${this.agentName}] Starting daemon...`);
    console.log(`[AgentTick:${this.agentName}] Workspace: ${this.config.workspaceRoot}`);
    console.log(`[AgentTick:${this.agentName}] Watch paths: ${this.config.watchPaths.length}`);

    // Initialize components
    await this.detector.initialize();

    // Load state from previous run
    const state = await this.stateManager.load();
    console.log(`[AgentTick:${this.agentName}] Loaded state: ${state.daemonState}`);

    // Start tick loop
    this.scheduleTick();

    // Graceful shutdown
    process.on('SIGTERM', () => this.stop());
    process.on('SIGINT', () => this.stop());

    console.log(`[AgentTick:${this.agentName}] Daemon started successfully (PID: ${process.pid})`);
  }

  scheduleTick() {
    const interval = this.scheduler.getNextInterval();
    this.tickTimer = setTimeout(() => this.tick(), interval);
  }

  async tick() {
    const tickStart = Date.now();
    this.tickCount++;

    try {
      // Detect events
      const events = await this.detector.detect();

      if (events.length > 0) {
        console.log(`[Tick:${this.agentName}] Detected ${events.length} events`);
        this.scheduler.markEvent();

        // Log event types
        events.forEach(e => {
          console.log(`  - ${e.type} (tier ${e.tier}): ${JSON.stringify(e.data).substring(0, 100)}`);
        });

        // Save events to state
        for (const event of events) {
          await this.stateManager.addPendingEvent(event);
        }
      }

      // Update state
      const state = await this.stateManager.load();
      state.lastTick = Date.now();
      state.daemonState = this.scheduler.getState();
      await this.stateManager.save(state);

      // Log tick complete (only if verbose or events detected)
      if (events.length > 0 || this.tickCount % 60 === 0) {
        const duration = Date.now() - tickStart;
        console.log(`[Tick:${this.agentName}] Complete (${duration}ms, state: ${this.scheduler.getState()}, count: ${this.tickCount})`);
      }

    } catch (error) {
      console.error(`[Tick:${this.agentName}] Error:`, error);
    } finally {
      this.scheduleTick();
    }
  }

  async stop() {
    console.log(`[AgentTick:${this.agentName}] Stopping daemon...`);

    if (this.tickTimer) {
      clearTimeout(this.tickTimer);
    }

    await this.detector.stop();

    console.log(`[AgentTick:${this.agentName}] Daemon stopped (total ticks: ${this.tickCount})`);
    process.exit(0);
  }
}

// Main entry point
async function main() {
  // Parse --agent=<name> argument
  const agentArg = process.argv.find(arg => arg.startsWith('--agent='));
  if (!agentArg) {
    console.error('Error: --agent=<name> argument required');
    console.error('Usage: node daemon.js --agent=mira');
    process.exit(1);
  }

  const agentName = agentArg.split('=')[1];
  if (!agentName) {
    console.error('Error: agent name cannot be empty');
    process.exit(1);
  }

  // Load agent-specific configuration
  const configPath = path.join(__dirname, 'agents', `${agentName}.json`);
  let agentConfig;

  try {
    const configData = await fs.readFile(configPath, 'utf-8');
    agentConfig = JSON.parse(configData);
  } catch (error) {
    console.error(`Error: Could not load config for agent "${agentName}"`);
    console.error(`  Looked for: ${configPath}`);
    console.error(`  ${error.message}`);
    process.exit(1);
  }

  // Validate config
  if (!agentConfig.workspaceRoot) {
    console.error('Error: workspaceRoot not defined in agent config');
    process.exit(1);
  }

  if (!agentConfig.watchPaths || agentConfig.watchPaths.length === 0) {
    console.error('Error: watchPaths not defined in agent config');
    process.exit(1);
  }

  // Create and start daemon
  const daemon = new AgentTickDaemon(agentConfig, agentName);

  // Event handlers
  daemon.detector.on('event', (event) => {
    // Event already logged in tick() - this is for future hooks
  });

  await daemon.start();
}

// Run if executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

export { AgentTickDaemon };
