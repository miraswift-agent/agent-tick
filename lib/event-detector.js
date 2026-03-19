/**
 * Event Detector
 * Detects events requiring attention or action
 */

import chokidar from 'chokidar';
import simpleGit from 'simple-git';
import { EventEmitter } from 'events';

export class EventDetector extends EventEmitter {
  constructor(config, agentName) {
    super();
    this.config = config;
    this.agentName = agentName;
    this.workspaceRoot = config.workspaceRoot;
    this.fileWatcher = null;
    this.detectedEvents = [];
  }

  async initialize() {
    console.log(`[EventDetector:${this.agentName}] Initializing file watcher...`);
    
    this.fileWatcher = chokidar.watch(this.config.watchPaths, {
      persistent: true,
      ignoreInitial: true,
      ignored: /(^|[\/\\])\../, // Ignore dotfiles
      awaitWriteFinish: {
        stabilityThreshold: 2000,
        pollInterval: 100
      }
    });

    this.fileWatcher.on('change', (path) => {
      this.addEvent({
        type: 'workspace:file_change',
        timestamp: Date.now(),
        tier: this.inferTier(path),
        data: { path },
        source: 'file_watcher'
      });
    });

    console.log(`[EventDetector:${this.agentName}] File watcher initialized for ${this.config.watchPaths.length} paths`);
  }

  async checkGitStatus() {
    if (!this.config.monitoring?.git?.enabled) {
      return null;
    }

    try {
      const git = simpleGit(this.workspaceRoot);
      const status = await git.status();

      if (!status.isClean()) {
        return {
          type: 'workspace:git_uncommitted',
          timestamp: Date.now(),
          tier: 2,
          data: {
            files: status.files.map(f => f.path),
            ahead: status.ahead,
            behind: status.behind
          },
          source: 'git_status'
        };
      }
    } catch (error) {
      // Git not available or not a repo - that's fine
    }

    return null;
  }

  inferTier(path) {
    if (path.includes('/journal/')) return 3;
    if (path.includes('/projects/')) return 2;
    if (path.includes('/memory/')) return 2;
    return 3;
  }

  addEvent(event) {
    this.detectedEvents.push(event);
    this.emit('event', event);
  }

  async detect() {
    const events = [...this.detectedEvents];
    this.detectedEvents = [];

    // Check git status
    const gitEvent = await this.checkGitStatus();
    if (gitEvent) events.push(gitEvent);

    return events;
  }

  async stop() {
    if (this.fileWatcher) {
      await this.fileWatcher.close();
      console.log(`[EventDetector:${this.agentName}] File watcher stopped`);
    }
  }
}
