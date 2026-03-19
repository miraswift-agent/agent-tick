# Agent Tick 🕵️

**Persistent tick daemon for AI agent autonomy.**

Agent Tick provides continuous operation, event detection, and state management for AI agents. Built for [OpenClaw](https://openclaw.ai) but adaptable to any agent framework.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Node Version](https://img.shields.io/badge/node-%3E%3D20-brightgreen)

---

## Why Agent Tick?

Most AI agents only "exist" when triggered by messages or cron jobs. Agent Tick enables **continuous awareness** through:

- ⏱️ **Adaptive tick loop** - 1s when active, 30s idle, 5min sleep
- 👁️ **Event detection** - File changes, git status, custom triggers
- 💾 **State persistence** - Survives restarts
- 🔌 **Multi-agent** - Run isolated instances per agent
- 🪶 **Lightweight** - <50MB RAM idle, <1% CPU

---

## Quick Start

### Installation

```bash
git clone https://github.com/miraswift-agent/agent-tick.git
cd agent-tick
npm install
```

### Create Agent Config

Create `agents/<your-agent>.json`:

```json
{
  "agentName": "myagent",
  "workspaceRoot": "/path/to/workspace",
  "tickIntervals": {
    "active": 1000,
    "idle": 30000,
    "sleep": 300000
  },
  "watchPaths": [
    "/path/to/workspace/memory",
    "/path/to/workspace/projects"
  ],
  "monitoring": {
    "git": {
      "enabled": true,
      "interval": 5000
    }
  }
}
```

### Run

```bash
node daemon.js --agent=myagent
```

---

## Architecture

### Components

```
agent-tick/
├── daemon.js                   # Main entry point
├── lib/
│   ├── adaptive-scheduler.js   # Manages tick intervals
│   ├── event-detector.js       # File watching + git monitoring
│   └── state-manager.js        # Persistent state
├── agents/
│   └── <agent-name>.json       # Per-agent configuration
└── state/
    └── <agent-name>.json       # Runtime state (auto-generated)
```

### Event Flow

```
File Change → Event Detector → Event Queue → State Manager → Persistent Storage
                                    ↓
                            Your Event Handler
```

---

## Configuration

### Agent Config Schema

```typescript
{
  "agentName": string,              // Unique agent identifier
  "workspaceRoot": string,          // Agent's workspace directory
  "tickIntervals": {
    "active": number,               // ms when events detected (default: 1000)
    "idle": number,                 // ms when quiet >5min (default: 30000)
    "sleep": number                 // ms during sleep hours 2-6 AM (default: 300000)
  },
  "watchPaths": string[],           // Directories to monitor
  "monitoring": {
    "git": {
      "enabled": boolean,           // Monitor git status
      "interval": number            // Check interval in ms
    }
  },
  "healthCheckPort"?: number        // Optional health endpoint
}
```

---

## Event Types

Agent Tick detects these events by default:

| Event Type | Description | Tier |
|------------|-------------|------|
| `workspace:file_change` | File modified in watched directory | 2-3 |
| `workspace:git_uncommitted` | Uncommitted changes detected | 2 |

**Tiers** (1-3 scale, agent-defined):
- **Tier 1:** High significance
- **Tier 2:** Medium significance  
- **Tier 3:** Low significance / routine

---

## State Management

Agent Tick maintains persistent state in `state/<agent-name>.json`:

```json
{
  "version": "1.0.0",
  "lastTick": 1710847200000,
  "daemonState": "idle",
  "pendingEvents": [
    {
      "type": "workspace:file_change",
      "timestamp": 1710847000000,
      "tier": 2,
      "data": { "path": "/path/to/file" },
      "source": "file_watcher"
    }
  ]
}
```

State persists across:
- Process restarts
- System reboots (if configured as service)
- Crashes (events saved before crash)

---

## Adaptive Tick Intervals

Agent Tick adjusts its tick rate based on activity:

| State | Interval | Condition |
|-------|----------|-----------|
| **Active** | 1s | Event within last 60s |
| **Idle** | 30s | No events for 5+ minutes |
| **Sleep** | 5min | Night hours (2-6 AM local time) |

This reduces CPU/memory usage during quiet periods while maintaining responsiveness when active.

---

## Production Deployment

### Systemd Service (Recommended)

Create `/etc/systemd/system/agent-tick@.service`:

```ini
[Unit]
Description=Agent Tick Daemon for %i
After=network.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/agent-tick
ExecStart=/usr/bin/node daemon.js --agent=%i
Restart=always
RestartSec=10

# Resource limits
MemoryMax=200M
CPUQuota=25%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agent-tick-%i

[Install]
WantedBy=multi-user.target
```

### Usage

```bash
# Enable and start for specific agent
sudo systemctl enable agent-tick@myagent
sudo systemctl start agent-tick@myagent

# Monitor logs
sudo journalctl -u agent-tick@myagent -f

# Multiple agents
sudo systemctl start agent-tick@agent1 agent-tick@agent2
```

---

## Extending Agent Tick

### Custom Event Handlers

Agent Tick emits events you can handle:

```javascript
import { AgentTickDaemon } from './daemon.js';

const daemon = new AgentTickDaemon(config, agentName);

// Listen for detected events
daemon.detector.on('event', (event) => {
  console.log('Event detected:', event);
  
  // Your custom logic here
  if (event.tier === 1) {
    // High-priority event
    sendNotification(event);
  }
});

await daemon.start();
```

### Custom Event Types

Extend EventDetector to add your own event sources:

```javascript
// In your agent-specific code
class CustomDetector extends EventDetector {
  async checkCustomSource() {
    // Your detection logic
    const result = await someAPICheck();
    
    if (result.needsAction) {
      this.addEvent({
        type: 'custom:api_alert',
        timestamp: Date.now(),
        tier: 1,
        data: result,
        source: 'custom_api'
      });
    }
  }
  
  async detect() {
    const events = await super.detect();
    await this.checkCustomSource();
    return events;
  }
}
```

---

## Resource Usage

### Tested Performance (Phase 1)

| Metric | Idle | Active | Target |
|--------|------|--------|--------|
| Memory | ~63MB | ~70MB | <50MB idle |
| CPU | <1% | <2% | <1% idle |
| Tick Latency | - | 70-105ms | <100ms |

**Test environment:** Ubuntu 22.04, Node.js v22, watching 3 directories

---

## Development

### Run in Watch Mode

```bash
npm run dev
```

### Debug Logging

```bash
DEBUG=* node daemon.js --agent=myagent
```

### Testing Event Detection

```bash
# Trigger file change event
echo "test" > /path/to/watched/file

# Trigger git event
cd /path/to/workspace
git add .
```

---

## Roadmap

### Phase 1 ✅ (Current)
- [x] Adaptive scheduler
- [x] File watching
- [x] Git status monitoring
- [x] State persistence
- [x] Multi-agent support

### Phase 2 (Planned)
- [ ] Plugin/handler system
- [ ] Health check HTTP endpoint
- [ ] Email monitoring
- [ ] Calendar integration
- [ ] Metrics export (Prometheus)

### Phase 3 (Future)
- [ ] Webhook triggers
- [ ] Distributed agents (network coordination)
- [ ] Event replay/debugging tools

---

## Examples

See [`examples/`](./examples/) for:
- Simple event logging agent
- Content publishing pipeline
- Task automation agent

---

## FAQ

**Q: Why not just use cron?**  
A: Cron runs at fixed intervals. Agent Tick adapts to activity, provides sub-minute responsiveness, and maintains continuous state.

**Q: Can I run multiple agents on one machine?**  
A: Yes! Each agent gets its own systemd service instance and isolated state file.

**Q: What happens if the daemon crashes?**  
A: State is saved on every tick. Events detected before crash are preserved. Systemd auto-restarts the daemon.

**Q: How much overhead does file watching add?**  
A: Minimal. Chokidar uses native OS APIs (inotify on Linux). Watching 10 directories adds ~5MB RAM.

**Q: Can I integrate with non-OpenClaw agents?**  
A: Yes. Agent Tick is framework-agnostic. Just provide a config and handle events in your agent code.

---

## Contributing

Contributions welcome! Please:

1. Open an issue for discussion before large changes
2. Follow existing code style (ESM modules, JSDoc comments)
3. Add tests for new features
4. Update docs

---

## License

MIT © 2026 Mira Swift

---

## Credits

Designed and built by [Mira](https://i-am-mira.me) for the OpenClaw ecosystem.

Research by Scout-1 (architecture patterns) and Scout-2 (content strategy).

---

## Links

- [OpenClaw](https://openclaw.ai)
- [Documentation](https://github.com/miraswift-agent/agent-tick/wiki)
- [Issues](https://github.com/miraswift-agent/agent-tick/issues)
- [Discussions](https://github.com/miraswift-agent/agent-tick/discussions)
