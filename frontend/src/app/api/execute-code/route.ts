import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import CodeInterpreter from "@e2b/code-interpreter";

/**
 * Supported programming languages for code execution
 */
type SupportedLanguage = "javascript" | "python";

/**
 * Request payload structure for code execution
 */
interface ExecutionRequest {
  code: string;
  language: SupportedLanguage;
}

/**
 * Code execution result format from E2B
 */
interface ExecutionResult {
  stdout?: string[];
  stderr?: string[];
  error?: string | object;
}

/**
 * Custom error class for validation errors
 */
class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

/**
 * Route handler for POST requests to execute code
 */
export async function POST(request: NextRequest) {
  try {
    // Get API key from Authorization header
    const authHeader = request.headers.get("Authorization");

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      throw new ValidationError("API key is required in Authorization header");
    }

    const apiKey = authHeader.substring(7); // Remove "Bearer " prefix

    if (!apiKey) {
      throw new Error("API key is not provided");
    }

    // Parse and validate request body
    const body = await request.json();
    const { code, language } = validateRequestBody(body);

    // Initialize E2B session with appropriate template
    const session = await createCodeInterpreterSession(language, apiKey);

    try {
      // Execute the code and process the result
      const result = await executeCode(session, code, language);
      const formattedOutput = formatExecutionOutput(result);

      // Return successful response
      return NextResponse.json({
        output: formattedOutput,
        success: true,
      });
    } finally {
      // Always close the session to prevent resource leaks
      await closeSession(session);
    }
  } catch (error) {
    // Handle and format errors appropriately
    const { statusCode, errorResponse } = handleExecutionError(error);
    return NextResponse.json(errorResponse, { status: statusCode });
  }
}

/**
 * Validates the request body and returns the validated data
 * Throws error if validation fails
 */
function validateRequestBody(body: any): ExecutionRequest {
  const { code, language } = body as Partial<ExecutionRequest>;

  if (!code || typeof code !== "string") {
    throw new ValidationError("Code must be provided as a string");
  }

  if (!language || !["javascript", "python"].includes(language)) {
    throw new ValidationError(
      "Language must be either 'javascript' or 'python'"
    );
  }

  return { code, language } as ExecutionRequest;
}

/**
 * Creates and returns a new code interpreter session
 */
async function createCodeInterpreterSession(
  language: SupportedLanguage,
  apiKey: string
) {
  const template = language === "javascript" ? "nodejs" : "python";

  try {
    // Create the session with proper configuration and required parameters
    return await CodeInterpreter.create(template, {
      apiKey: "e2b_8ee1b75c2da2083a3d0cd2722f25bdbafa5a94e0",
      metadata: {
        name: `${language}-execution-session`,
      },
    });
  } catch (error) {
    console.error("E2B Session Creation Error:", error);
    throw new Error(
      `Failed to initialize code interpreter: ${getErrorMessage(error)}`
    );
  }
}

/**
 * Executes the provided code using the E2B session
 */
async function executeCode(
  session: any,
  code: string,
  language: SupportedLanguage
): Promise<ExecutionResult> {
  try {
    if (language === "javascript") {
      return await session.runJs(code);
    } else {
      return await session.runPython(code);
    }
  } catch (error) {
    throw new Error(`Code execution failed: ${getErrorMessage(error)}`);
  }
}

/**
 * Safely closes an E2B session
 */
async function closeSession(session: any): Promise<void> {
  try {
    await session.close();
  } catch (error) {
    console.warn("Failed to close E2B session:", getErrorMessage(error));
  }
}

/**
 * Formats the output from code execution into a readable string
 */
function formatExecutionOutput(result: ExecutionResult): string {
  if (!result) {
    return "No output received from execution";
  }

  const outputParts: string[] = [];

  // Add standard output if available
  if (result.stdout?.length) {
    outputParts.push(result.stdout.join("\n"));
  }

  // Add standard error if available
  if (result.stderr?.length) {
    outputParts.push("Errors:\n" + result.stderr.join("\n"));
  }

  // Add execution error if available
  if (result.error) {
    const errorText =
      typeof result.error === "string"
        ? result.error
        : JSON.stringify(result.error, null, 2);
    outputParts.push("Execution Error:\n" + errorText);
  }

  return outputParts.length > 0
    ? outputParts.join("\n\n")
    : "Code executed successfully with no output";
}

/**
 * Handles API execution errors and returns appropriate response
 */
function handleExecutionError(error: unknown): {
  statusCode: number;
  errorResponse: { message: string; success: false; code: string };
} {
  console.error("Code execution API error:", error);

  if (error instanceof ValidationError) {
    return {
      statusCode: 400,
      errorResponse: {
        message: error.message,
        success: false,
        code: "VALIDATION_ERROR",
      },
    };
  }

  // Check for environment variable error
  const errorMessage = getErrorMessage(error);
  if (errorMessage.includes("API key is not provided")) {
    return {
      statusCode: 401,
      errorResponse: {
        message: "API key is required",
        success: false,
        code: "API_KEY_MISSING",
      },
    };
  }

  // Check for specific E2B API key errors
  if (
    errorMessage.includes("Invalid API key") ||
    errorMessage.includes("authorization header")
  ) {
    return {
      statusCode: 401,
      errorResponse: {
        message: "Invalid API key. Please check your API key and try again.",
        success: false,
        code: "INVALID_API_KEY",
      },
    };
  }

  return {
    statusCode: 500,
    errorResponse: {
      message: `An unexpected error occurred: ${errorMessage}`,
      success: false,
      code: "INTERNAL_SERVER_ERROR",
    },
  };
}

/**
 * Extracts a message from any error type
 */
function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
