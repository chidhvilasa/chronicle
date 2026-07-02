import { Inspector } from "./components/Inspector";
import { MainPanel } from "./components/MainPanel";
import { RunList } from "./components/RunList";
import { Toast } from "./components/Toast";
import { TopNav } from "./components/TopNav";
import { useServerStartupError } from "./hooks/useServerStartupError";
import "./App.css";

function App() {
  const serverStartupError = useServerStartupError();

  return (
    <div className="app">
      <TopNav />
      {serverStartupError !== null && (
        <p className="app-error" role="alert">
          {serverStartupError}
        </p>
      )}
      <div className="app-body">
        <RunList />
        <MainPanel />
        <Inspector />
      </div>
      <Toast />
    </div>
  );
}

export default App;
