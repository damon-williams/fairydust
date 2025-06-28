import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { navigation } from '@/lib/navigation';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sparkles, Menu, X, LogOut } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();

  return (
    <div className={cn(
      "flex flex-col h-screen bg-gradient-to-b from-slate-900 to-slate-800 border-r border-slate-700 transition-all duration-300",
      collapsed ? "w-16" : "w-72",
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        {!collapsed && (
          <div className="flex items-center space-x-2">
            <Sparkles className="h-8 w-8 text-yellow-400" />
            <div>
              <h1 className="text-xl font-bold text-white fairy-dust">
                fairydust
              </h1>
              <p className="text-sm text-slate-400">Admin Portal</p>
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCollapsed(!collapsed)}
          className="text-slate-400 hover:text-white hover:bg-slate-700"
        >
          {collapsed ? <Menu className="h-4 w-4" /> : <X className="h-4 w-4" />}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                "flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                "hover:bg-slate-700 hover:text-white",
                isActive 
                  ? "bg-slate-700 text-white shadow-lg" 
                  : "text-slate-300",
                collapsed && "justify-center"
              )}
            >
              <item.icon className={cn("h-5 w-5", !collapsed && "mr-3")} />
              {!collapsed && (
                <>
                  <span className="flex-1">{item.name}</span>
                  <div className="flex items-center space-x-1">
                    {item.new && (
                      <Badge variant="secondary" className="text-xs bg-blue-600 text-white">
                        NEW
                      </Badge>
                    )}
                    {item.badge && item.badge > 0 && (
                      <Badge variant="destructive" className="text-xs">
                        {item.badge}
                      </Badge>
                    )}
                    {item.status && (
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        item.status === 'online' && "bg-green-500",
                        item.status === 'degraded' && "bg-yellow-500",
                        item.status === 'offline' && "bg-red-500"
                      )} />
                    )}
                  </div>
                </>
              )}
            </Link>
          );
        })}
      </nav>

      {/* User Section */}
      <div className="p-4 border-t border-slate-700">
        {!collapsed ? (
          <div className="space-y-3">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                <span className="text-sm font-medium text-white">
                  {user?.fairyname?.charAt(0).toUpperCase() || 'A'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  {user?.fairyname || 'Admin User'}
                </p>
                <p className="text-xs text-slate-400 truncate">
                  {user?.email || 'admin@fairydust.fun'}
                </p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="w-full text-slate-300 hover:text-white hover:bg-slate-700 justify-start"
            >
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
            {/* Version Info */}
            <div className="text-center pt-2 border-t border-slate-700">
              <p className="text-xs text-slate-500">
                Admin Portal v2.1.0
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex justify-center">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                <span className="text-sm font-medium text-white">
                  {user?.fairyname?.charAt(0).toUpperCase() || 'A'}
                </span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="w-full text-slate-300 hover:text-white hover:bg-slate-700 justify-center p-2"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}