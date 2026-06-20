import { NextResponse } from "next/server";

export async function GET() {
  try {
    const response = NextResponse.json({ success: true, message: "Logged out successfully" });
    
    // Securely clear cookies
    response.cookies.delete("upgrade-token");
    response.cookies.delete("upgrade-user");
    
    return response;
  } catch (error) {
    console.error("Logout error:", error);
    return NextResponse.json(
      { error: "Failed to logout" },
      { status: 500 }
    );
  }
}

export async function POST() {
    return GET();
}