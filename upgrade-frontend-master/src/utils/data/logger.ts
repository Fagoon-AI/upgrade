// @/utils/logger.ts

type LogLevel = "info" | "error" | "warn" | "debug";

interface LogMessage {
  level: LogLevel;
  message: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

class Logger {
  private logToConsole(logMessage: LogMessage) {
    const { level, message, timestamp, metadata } = logMessage;
    console[level](`[${timestamp}] ${message}`, metadata || "");
  }

  public info(message: string, metadata?: Record<string, any>) {
    this.logToConsole({
      level: "info",
      message,
      timestamp: new Date().toISOString(),
      metadata,
    });
  }

  public error(message: string, metadata?: Record<string, any>) {
    this.logToConsole({
      level: "error",
      message,
      timestamp: new Date().toISOString(),
      metadata,
    });
  }
}

export const logger = new Logger();
