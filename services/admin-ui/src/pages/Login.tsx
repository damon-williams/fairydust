import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Sparkles, Mail, Lock } from 'lucide-react';
import { toast } from 'sonner';

export function Login() {
  const { requestOTP, login, isLoading } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [otp, setOtp] = useState('');
  const [step, setStep] = useState<'identifier' | 'otp'>('identifier');
  const [error, setError] = useState('');

  // Debug logging
  console.log('🔍 LOGIN_DEBUG: Login component loaded with Quick Fill button v2.1.4');
  console.log('🔍 LOGIN_DEBUG: Build timestamp:', new Date().toISOString());

  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim()) {
      setError('Please enter your email address');
      return;
    }

    setError('');
    const success = await requestOTP(identifier.trim());
    
    if (success) {
      setStep('otp');
      toast.success('OTP sent successfully!');
    } else {
      setError('Failed to send OTP. Please try again.');
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp.trim()) {
      setError('Please enter the OTP code');
      return;
    }

    setError('');
    const success = await login(identifier, otp.trim());
    
    if (!success) {
      setError('Invalid OTP or insufficient admin permissions');
    }
  };

  const isEmail = identifier.includes('@');

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="absolute inset-0 opacity-20" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%239C92AC' fill-opacity='0.1'%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`
      }}></div>
      
      <Card className="w-full max-w-md mx-4 bg-white/95 backdrop-blur-sm shadow-2xl border-0">
        <CardHeader className="text-center space-y-4">
          <div className="flex justify-center">
            <div className="w-16 h-16 bg-gradient-to-br from-yellow-400 to-orange-500 rounded-full flex items-center justify-center">
              <Sparkles className="h-8 w-8 text-white" />
            </div>
          </div>
          
          <div>
            <CardTitle className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
              fairydust
            </CardTitle>
            <CardDescription className="text-base text-slate-600">
              Admin Portal
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {error && (
            <Alert className="border-red-200 bg-red-50">
              <AlertDescription className="text-red-700">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {step === 'identifier' ? (
            <form onSubmit={handleRequestOTP} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">
                  Email Address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Mail className="h-4 w-4 text-slate-400" />
                  </div>
                  <Input
                    type="text"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="Enter your email address"
                    className="pl-10"
                    disabled={isLoading}
                    required
                  />
                </div>
              </div>

              {/* Temporary development shortcut */}
              <Button 
                type="button" 
                variant="outline" 
                size="sm"
                className="w-full text-xs bg-yellow-50 border-yellow-200 text-yellow-800 hover:bg-yellow-100"
                onClick={() => setIdentifier('damonw@gmail.com')}
                disabled={isLoading}
              >
                🚀 Quick Fill (Dev)
              </Button>

              <Button 
                type="submit" 
                className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                disabled={isLoading}
              >
                {isLoading ? 'Sending...' : 'Send OTP'}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">
                  OTP Code
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-4 w-4 text-slate-400" />
                  </div>
                  <Input
                    type="text"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    placeholder="Enter 6-digit code"
                    className="pl-10 text-center tracking-wider"
                    maxLength={6}
                    disabled={isLoading}
                    required
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Check your email for the verification code
                </p>
              </div>

              <div className="space-y-3">
                <Button 
                  type="submit" 
                  className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                  disabled={isLoading}
                >
                  {isLoading ? 'Verifying...' : 'Login'}
                </Button>
                
                <Button 
                  type="button" 
                  variant="outline" 
                  className="w-full"
                  onClick={() => {
                    setStep('identifier');
                    setOtp('');
                    setError('');
                  }}
                  disabled={isLoading}
                >
                  Back
                </Button>
              </div>
            </form>
          )}

          <div className="text-center">
            <p className="text-xs text-slate-500">
              Admin access required. Contact support if you need assistance.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}