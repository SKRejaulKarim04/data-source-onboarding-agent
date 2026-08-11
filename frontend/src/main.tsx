import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/primitives.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Missing #root — index.html is not the one Vite built.");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
