import {
  BarChart3,
  Users,
  Smartphone,
  Brain,
  Activity,
  Settings
} from 'lucide-react';

export interface NavigationItem {
  name: string;
  href: string;
  icon: any;
  current?: boolean;
  badge?: number;
  status?: 'online' | 'offline' | 'degraded';
  new?: boolean;
}

export const navigation: NavigationItem[] = [
  {
    name: 'Dashboard',
    href: '/admin/dashboard',
    icon: BarChart3,
  },
  {
    name: 'Users',
    href: '/admin/users',
    icon: Users,
  },
  {
    name: 'Apps',
    href: '/admin/apps',
    icon: Smartphone,
  },
  {
    name: 'LLM Analytics',
    href: '/admin/llm',
    icon: Brain,
    new: true,
  },
  {
    name: 'System Status',
    href: '/admin/system',
    icon: Activity,
  },
  {
    name: 'Settings',
    href: '/admin/settings',
    icon: Settings,
  },
];

export const userNavigation = [
  { name: 'Your Profile', href: '#' },
  { name: 'Settings', href: '#' },
  { name: 'Sign out', href: '/admin/logout' },
];