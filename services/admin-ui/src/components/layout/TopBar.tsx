import { useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';

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
        {/* Page Title */}
        <div className="flex items-center">
          <h1 className="text-2xl font-semibold text-slate-900">
            {getPageTitle()}
          </h1>
        </div>

        {/* Actions */}
        <div className="flex items-center space-x-3">
          {/* Future actions can go here */}
        </div>
      </div>
    </header>
  );
}