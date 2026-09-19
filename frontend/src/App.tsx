import { HealthStatus } from './components/HealthStatus.tsx'

function App() {
  return (
    <main>
      <h1>DataClarity</h1>
      <HealthStatus baseUrl={import.meta.env.VITE_API_BASE_URL} />
    </main>
  )
}

export default App
