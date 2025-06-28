import { useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Search, 
  RefreshCw
} from 'lucide-react';

export function TopBar() {
  const location = useLocation();
  
  const getPageTitle = () => {
    const path = location.pathname;
    if (path.includes('/dashboard')) return 'Dashboard';
    if (path.includes('/users')) return 'Users';
    if (path.includes('/apps')) return 'Apps';
    if (path.includes('/llm')) return 'LLM Analytics';
    if (path.includes('/system')) return 'System Status';
    if (path.includes('/settings')) return 'Settings';
    return 'Admin Portal';
  };

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Page Title & Search */}
        <div className="flex items-center space-x-4">
          <h1 className="text-2xl font-semibold text-slate-900">
            {getPageTitle()}
          </h1>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
            <Input
              placeholder="Search..."
              className="pl-10 w-64 bg-slate-50 border-slate-200"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center space-x-3">
          {/* Refresh */}
          <Button variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>
    </header>
  );
}