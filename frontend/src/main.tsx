import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ApiError } from "./api/client";
import { ToastProvider } from "./components/ui";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && n < 2,
      refetchOnWindowFocus: false,
    },
  },
});

// A 401 anywhere means the session ended: send the user back to the login screen.
queryClient.getQueryCache().subscribe((e) => {
  const err = e.query.state.error;
  if (err instanceof ApiError && err.status === 401 && e.query.queryKey[0] !== "auth") {
    queryClient.invalidateQueries({ queryKey: ["auth"] });
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <App />
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
