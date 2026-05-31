import { useState, useEffect } from "react";
import { Check, Loader2 } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

const STEPS = [
  { label: "Fetching transcripts & metadata", duration: 20 },
  { label: "Embedding with BGE-M3", duration: 20 },
  { label: "Storing in Pinecone", duration: 20 },
];

export default function IngestProgressIndicator() {
  const ingesting = useEngageStore((s) => s.ingesting);
  const [activeStep, setActiveStep] = useState(-1);

  useEffect(() => {
    if (!ingesting) {
      setActiveStep(-1);
      return;
    }

    setActiveStep(0);
    
    const t1 = setTimeout(() => setActiveStep(1), 20000);
    const t2 = setTimeout(() => setActiveStep(2), 40000);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [ingesting]);

  if (!ingesting) return null;

  return (
    <div className="bg-white border-t border-gray-200 p-4 space-y-3">
      {STEPS.map((step, index) => (
        <div className="flex items-center gap-3" key={index}>
          <div className="w-6 h-6 flex items-center justify-center">
            {activeStep > index ? (
              <Check size={16} className="text-green-500" />
            ) : activeStep === index ? (
              <Loader2 size={16} className="animate-spin text-blue-500" />
            ) : (
              <div className="w-2 h-2 rounded-full bg-gray-300" />
            )}
          </div>
          <span
            className={`text-sm ${
              activeStep > index
                ? "text-green-700"
                : activeStep === index
                ? "text-blue-700 font-medium"
                : "text-gray-400"
            }`}
          >
            {step.label}
          </span>
        </div>
      ))}
    </div>
  );
}
