import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "react-hot-toast"
import Landing from "./pages/Landing"
import ErrorBanner from "./components/shared/ErrorBanner"

const Chat = lazy(() => import("./pages/Chat"))

function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 4000,
          style: { fontSize: "14px" },
        }}
      />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/chat"
          element={
            <Suspense fallback={
              <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <p className="text-sm text-gray-400">Loading chat...</p>
              </div>
            }>
              <Chat />
            </Suspense>
          }
        />
      </Routes>
      <ErrorBanner />
    </BrowserRouter>
  )
}

export default App