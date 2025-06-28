import { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface StatsCardProps {
  title: string;
  value: string | number;
  change?: {
    value: number;
    trend: 'up' | 'down' | 'neutral';
    period: string;
  };
  icon: ReactNode;
  gradient?: string;
  className?: string;
}

export function StatsCard({ 
  title, 
  value, 
  change, 
  icon, 
  gradient = "from-blue-500 to-blue-600",
  className 
}: StatsCardProps) {
  return (
    <Card className={cn("relative overflow-hidden", className)}>
      <div className={cn("absolute inset-0 bg-gradient-to-br opacity-5", gradient)} />
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-slate-600">
          {title}
        </CardTitle>
        <div className={cn("p-2 rounded-lg bg-gradient-to-br text-white", gradient)}>
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold text-slate-900">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        {change && (
          <div className="flex items-center space-x-2 mt-2">
            <Badge 
              variant={change.trend === 'up' ? 'default' : change.trend === 'down' ? 'destructive' : 'secondary'}
              className="text-xs"
            >
              {change.trend === 'up' ? '+' : change.trend === 'down' ? '-' : ''}
              {Math.abs(change.value)}%
            </Badge>
            <span className="text-xs text-slate-500">from {change.period}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}