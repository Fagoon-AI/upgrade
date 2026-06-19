"use client";
import React, { useState } from "react";
import { Loader2 } from "lucide-react";

interface VerificationResult {
  factual_accuracy: string;
  ground_truth: string;
  confidence_score: number;
}

interface ApiResponse {
  provided_response: string;
  internet_search_response: string;
  verification_result: VerificationResult;
}

const ChatEvalPage = () => {
  const [query, setQuery] = useState<string>("");
  const [response, setResponse] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch(
        "/chateval/api/chat/evaluate",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ user_query: query }),
        },
      );

      if (!res.ok) {
        throw new Error("Failed to fetch response");
      }

      const data: ApiResponse = await res.json();
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const renderConfidenceScore = (score: number) => {
    const getColor = () => {
      if (score >= 80) return "bg-green-100 text-green-800";
      if (score >= 60) return "bg-yellow-100 text-yellow-800";
      return "bg-red-100 text-red-800";
    };

    return (
      <span
        className={`px-2 py-1 rounded-full text-sm font-medium ${getColor()}`}
      >
        {score}%
      </span>
    );
  };

  const ResponseSection = ({
    label,
    content,
  }: {
    label: string;
    content: string;
  }) => (
    <div className="flex flex-col gap-2">
      <div className="text-gray-700">{label}</div>
      <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-700">
        {content}
      </div>
    </div>
  );

  return (
    <div className="min-h-full border-l-[#e5e6e9] p-5 border-[1px] bg-white w-[20vw] min-w-[250px]">
      <div className="font-bold text-xl text-gray-700 mb-4">
        Chat Evaluation
      </div>

      <div className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex flex-col gap-2">
            <div className="text-gray-700">Query</div>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your query..."
              className="w-full min-h-[100px] p-3 bg-white border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className={`w-full py-3 px-4 rounded-lg text-white font-medium transition-colors ${
              loading || !query.trim()
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-gradient-to-r from-[#ec612c] to-[#f29571] hover:opacity-90"
            }`}
          >
            {loading ? (
              <div className="flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing...</span>
              </div>
            ) : (
              "Submit Query"
            )}
          </button>
        </form>

        {error && (
          <div className="text-red-500 text-sm bg-red-50 p-3 rounded-lg">
            {error}
          </div>
        )}

        {response && (
          <div className="space-y-4">
            <ResponseSection
              label="Provided Response"
              content={response.provided_response}
            />

            <ResponseSection
              label="Internet Search Response"
              content={response.internet_search_response}
            />

            <div className="flex flex-col gap-2">
              <div className="text-gray-700">Verification Results</div>
              <div className="space-y-3 p-3 bg-gray-50 rounded-lg text-sm">
                <div className="flex flex-col gap-1">
                  <span className="text-gray-500">Factual Accuracy</span>
                  <p className="text-gray-700">
                    {response.verification_result.factual_accuracy}
                  </p>
                </div>

                <div className="flex flex-col gap-1">
                  <span className="text-gray-500">Ground Truth</span>
                  <p className="text-gray-700">
                    {response.verification_result.ground_truth}
                  </p>
                </div>

                <div className="flex flex-col gap-1">
                  <span className="text-gray-500">Confidence Score</span>
                  <div>
                    {renderConfidenceScore(
                      response.verification_result.confidence_score,
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatEvalPage;
