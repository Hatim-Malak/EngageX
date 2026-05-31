import UrlInputForm from "../components/landing/UrlInputForm"
import IngestProgressIndicator from "../components/landing/IngestProgressIndicator"
import SessionRestorePrompt from "../components/landing/SessionRestorePrompt"

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl">
        {/* Hero section */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight">
            EngageX
          </h1>
          <p className="mt-2 text-gray-600 text-lg">
            Compare YouTube and Instagram engagement with AI-powered analysis
          </p>
        </div>

        {/* Main card */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
          {/* Two-column layout on desktop, stacked on mobile */}
          <div className="flex flex-col md:flex-row">
            {/* Left: Form */}
            <div className="flex-1 p-6 md:p-8">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Analyze Your Videos
              </h2>
              <UrlInputForm />
            </div>

            {/* Right: Info / Steps */}
            <div className="flex-1 bg-gray-50 p-6 md:p-8 border-t md:border-t-0 md:border-l border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                How It Works
              </h2>
              <ol className="space-y-4">
                {[
                  ["Paste URLs", "Add a YouTube and Instagram Reel link"],
                  ["AI Analysis", "Our engine extracts transcripts, metadata, and engagement data"],
                  ["Smart Chat", "Ask questions and get comparative insights"],
                ].map(([title, desc], i) => (
                  <li key={i} className="flex gap-3">
                    <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-semibold">
                      {i + 1}
                    </span>
                    <div>
                      <p className="font-medium text-gray-900 text-sm">{title}</p>
                      <p className="text-gray-500 text-sm">{desc}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {/* Progress indicator (below card, only visible during ingestion) */}
          <IngestProgressIndicator />
        </div>

        {/* Session restore prompt below the main card */}
        <div className="mt-6">
          <SessionRestorePrompt />
        </div>
      </div>
    </div>
  )
}
