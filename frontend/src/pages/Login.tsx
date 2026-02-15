import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { useAuthStore } from '@/stores/auth';
import { login } from '@/api';
import { Bot, Lock } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const setToken = useAuthStore((s) => s.setToken);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;

    setLoading(true);
    try {
      const res = await login(username, password);
      setToken(res.access_token);
      toast('Login successful', 'success');
      navigate('/', { replace: true });
    } catch {
      toast('Invalid username or password', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo / Header */}
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/15">
            <Bot className="h-8 w-8 text-accent-light" />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-foreground">
            Agent Trader
          </h1>
          <p className="mt-1 text-sm text-muted">Sign in to access the dashboard</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-foreground">
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="admin"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-foreground">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="••••••••"
            />
          </div>

          <Button
            type="submit"
            loading={loading}
            disabled={!username || !password}
            icon={<Lock className="h-4 w-4" />}
            className="w-full justify-center"
          >
            Sign In
          </Button>
        </form>

        <p className="text-center text-xs text-muted">
          Credentials are configured in the server&apos;s <code className="text-accent-light">.env</code> file
        </p>
      </div>
    </div>
  );
}
