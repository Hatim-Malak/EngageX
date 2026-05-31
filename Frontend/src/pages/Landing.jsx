import UrlInputForm from "../components/landing/UrlInputForm";
import IngestProgressIndicator from "../components/landing/IngestProgressIndicator";
import SessionRestorePrompt from "../components/landing/SessionRestorePrompt";

export default function Landing() {
  return (
    <div className="min-h-screen bg-brand-dark text-white relative overflow-hidden flex flex-col items-center pt-16 md:pt-24 pb-12 px-4 selection:bg-brand-secondary selection:text-white">
      {/* Background radial gradients for depth */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-brand-primary opacity-20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-brand-secondary opacity-10 blur-[120px] pointer-events-none" />

      {/* Hero Section */}
      <div className="w-full max-w-3xl text-center mb-12 relative z-10">
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6">
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-light via-white to-brand-secondary drop-shadow-lg">
            EngageX
          </span>
        </h1>
        <p className="text-lg md:text-xl text-brand-light opacity-80 font-medium max-w-2xl mx-auto leading-relaxed">
          Unlock the ultimate comparison between your YouTube and Instagram videos. Let AI dissect engagement, transcripts, and metadata in seconds.
        </p>
      </div>

      {/* Centered Form Card (Glassmorphism) */}
      <div className="w-full max-w-lg relative z-10 mb-16">
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl p-6 md:p-8">
          <h2 className="text-xl font-bold text-white mb-6 text-center tracking-wide">
            Start Your Analysis
          </h2>
          <UrlInputForm />
          
          {/* Progress Indicator */}
          <div className="mt-6">
             <IngestProgressIndicator />
          </div>
        </div>

        {/* Session Restore Prompt */}
        <div className="mt-6">
          <SessionRestorePrompt />
        </div>
      </div>

      {/* How it Works - Horizontal Grid */}
      <div className="w-full max-w-5xl relative z-10">
        <h3 className="text-center text-sm font-bold text-brand-secondary uppercase tracking-widest mb-8">
          How It Works
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              step: "1",
              title: "Paste URLs",
              desc: "Drop a YouTube and an Instagram Reel link into the form.",
            },
            {
              step: "2",
              title: "AI Analysis",
              desc: "Our engine extracts transcripts, metadata, and calculates true engagement.",
            },
            {
              step: "3",
              title: "Smart Chat",
              desc: "Compare videos side-by-side and chat with our AI to uncover insights.",
            },
          ].map((item, i) => (
            <div
              key={i}
              className="bg-brand-primary/20 border border-brand-secondary/30 rounded-xl p-6 text-center hover:bg-brand-primary/30 transition-all duration-300"
            >
              <div className="w-10 h-10 mx-auto bg-gradient-to-br from-brand-secondary to-brand-primary text-white rounded-full flex items-center justify-center font-bold text-lg mb-4 shadow-lg">
                {item.step}
              </div>
              <h4 className="font-semibold text-brand-light text-lg mb-2">
                {item.title}
              </h4>
              <p className="text-sm text-gray-300 leading-relaxed">
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
