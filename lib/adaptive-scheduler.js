/**
 * Adaptive Scheduler
 * Manages tick intervals based on activity level and time of day
 */

export class AdaptiveScheduler {
  constructor(config) {
    this.intervals = config.tickIntervals || {
      active: 1000,
      idle: 30000,
      sleep: 300000
    };
    this.lastEventTime = Date.now();
    this.currentState = 'idle';
  }

  getNextInterval() {
    const hour = new Date().getHours();
    const timeSinceEvent = Date.now() - this.lastEventTime;

    // Sleep mode: 2 AM - 6 AM
    if (hour >= 2 && hour < 6) {
      this.currentState = 'sleep';
      return this.intervals.sleep;
    }

    // Active mode: event within last minute
    if (timeSinceEvent < 60 * 1000) {
      this.currentState = 'active';
      return this.intervals.active;
    }

    // Idle mode: no events for 5+ minutes
    if (timeSinceEvent > 5 * 60 * 1000) {
      this.currentState = 'idle';
      return this.intervals.idle;
    }

    // Default: standard monitoring
    return 5000;
  }

  markEvent() {
    this.lastEventTime = Date.now();
  }

  getState() {
    return this.currentState;
  }
}
