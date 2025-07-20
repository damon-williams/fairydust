import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  FileText, 
  Plus, 
  Edit, 
  Eye, 
  Users, 
  CheckCircle, 
  AlertTriangle,
  Calendar,
  ExternalLink
} from 'lucide-react';
import { TermsDocument, TermsDocumentCreate, UserTermsAcceptance, TermsComplianceStats } from '@/types/admin';
import { adminApi } from '@/lib/admin-api';
import { toast } from 'sonner';

export default function Terms() {
  const [documents, setDocuments] = useState<TermsDocument[]>([]);
  const [acceptances, setAcceptances] = useState<UserTermsAcceptance[]>([]);
  const [stats, setStats] = useState<TermsComplianceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<TermsDocument | null>(null);
  const [acceptancesLoading, setAcceptancesLoading] = useState(false);

  // Form state for creating new documents
  const [newDocument, setNewDocument] = useState<TermsDocumentCreate>({
    document_type: 'terms_of_service',
    version: '',
    title: '',
    content_url: '',
    content_hash: '',
    requires_acceptance: true,
    effective_date: new Date().toISOString().split('T')[0]
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [docsData, statsData] = await Promise.all([
        adminApi.getTermsDocuments(),
        adminApi.getTermsStats()
      ]);
      setDocuments(docsData);
      setStats(statsData);
    } catch (error) {
      console.error('Failed to fetch terms data:', error);
      toast.error('Failed to load terms data');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAcceptances = useCallback(async (documentId: string) => {
    try {
      setAcceptancesLoading(true);
      const data = await adminApi.getTermsAcceptances(documentId);
      setAcceptances(data);
    } catch (error) {
      console.error('Failed to fetch acceptances:', error);
      toast.error('Failed to load acceptance data');
    } finally {
      setAcceptancesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateDocument = async () => {
    try {
      if (!newDocument.version || !newDocument.title || !newDocument.content_url) {
        toast.error('Please fill in all required fields');
        return;
      }

      await adminApi.createTermsDocument(newDocument);
      toast.success('Terms document created successfully');
      setCreateDialogOpen(false);
      setNewDocument({
        document_type: 'terms_of_service',
        version: '',
        title: '',
        content_url: '',
        content_hash: '',
        requires_acceptance: true,
        effective_date: new Date().toISOString().split('T')[0]
      });
      await fetchData();
    } catch (error) {
      console.error('Failed to create document:', error);
      toast.error('Failed to create terms document');
    }
  };

  const handleActivateDocument = async (documentId: string) => {
    try {
      await adminApi.activateTermsDocument(documentId);
      toast.success('Document activated successfully');
      await fetchData();
    } catch (error) {
      console.error('Failed to activate document:', error);
      toast.error('Failed to activate document');
    }
  };

  const handleDeactivateDocument = async (documentId: string) => {
    try {
      await adminApi.deactivateTermsDocument(documentId);
      toast.success('Document deactivated successfully');
      await fetchData();
    } catch (error) {
      console.error('Failed to deactivate document:', error);
      toast.error('Failed to deactivate document');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading terms management...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Terms & Conditions Management</h1>
          <p className="text-gray-600 mt-1">Manage legal documents and track user acceptance</p>
        </div>
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Create Document
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Terms Document</DialogTitle>
              <DialogDescription>
                Create a new version of terms of service or privacy policy
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="document_type">Document Type</Label>
                  <Select 
                    value={newDocument.document_type} 
                    onValueChange={(value: 'terms_of_service' | 'privacy_policy') => 
                      setNewDocument(prev => ({ ...prev, document_type: value }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="terms_of_service">Terms of Service</SelectItem>
                      <SelectItem value="privacy_policy">Privacy Policy</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="version">Version</Label>
                  <Input
                    id="version"
                    value={newDocument.version}
                    onChange={(e) => setNewDocument(prev => ({ ...prev, version: e.target.value }))}
                    placeholder="e.g., 1.0.0"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  value={newDocument.title}
                  onChange={(e) => setNewDocument(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="e.g., fairydust Terms of Service"
                />
              </div>
              <div>
                <Label htmlFor="content_url">Content URL</Label>
                <Input
                  id="content_url"
                  value={newDocument.content_url}
                  onChange={(e) => setNewDocument(prev => ({ ...prev, content_url: e.target.value }))}
                  placeholder="https://fairydust.app/legal/terms-v1.0.html"
                />
              </div>
              <div>
                <Label htmlFor="content_hash">Content Hash (SHA-256)</Label>
                <Input
                  id="content_hash"
                  value={newDocument.content_hash}
                  onChange={(e) => setNewDocument(prev => ({ ...prev, content_hash: e.target.value }))}
                  placeholder="SHA-256 hash of document content"
                />
              </div>
              <div>
                <Label htmlFor="effective_date">Effective Date</Label>
                <Input
                  id="effective_date"
                  type="date"
                  value={newDocument.effective_date}
                  onChange={(e) => setNewDocument(prev => ({ ...prev, effective_date: e.target.value }))}
                />
              </div>
              <div className="flex items-center space-x-2">
                <Switch
                  id="requires_acceptance"
                  checked={newDocument.requires_acceptance}
                  onCheckedChange={(checked) => setNewDocument(prev => ({ ...prev, requires_acceptance: checked }))}
                />
                <Label htmlFor="requires_acceptance">Requires User Acceptance</Label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateDocument}>Create Document</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats Overview */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Total Documents</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_documents}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Active Documents</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">{stats.active_documents}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Total Acceptances</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_acceptances}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Compliance Rate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">{stats.compliance_rate.toFixed(1)}%</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Content */}
      <Tabs defaultValue="documents" className="space-y-4">
        <TabsList>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="acceptances">Recent Acceptances</TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Terms Documents</CardTitle>
              <CardDescription>
                Manage versions of your terms of service and privacy policy
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Effective Date</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell>
                        <Badge variant={doc.document_type === 'terms_of_service' ? 'default' : 'secondary'}>
                          {doc.document_type === 'terms_of_service' ? 'Terms' : 'Privacy'}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono">{doc.version}</TableCell>
                      <TableCell>{doc.title}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {doc.is_active ? (
                            <Badge className="bg-green-100 text-green-800">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Active
                            </Badge>
                          ) : (
                            <Badge variant="outline">
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              Inactive
                            </Badge>
                          )}
                          {doc.requires_acceptance && (
                            <Badge variant="outline" className="text-xs">
                              Requires Acceptance
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center text-sm text-gray-600">
                          <Calendar className="h-4 w-4 mr-1" />
                          {formatDate(doc.effective_date)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => window.open(doc.content_url, '_blank')}
                          >
                            <ExternalLink className="h-3 w-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setSelectedDocument(doc);
                              fetchAcceptances(doc.id);
                            }}
                          >
                            <Users className="h-3 w-3" />
                          </Button>
                          {doc.is_active ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleDeactivateDocument(doc.id)}
                            >
                              Deactivate
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => handleActivateDocument(doc.id)}
                            >
                              Activate
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {documents.length === 0 && (
                <div className="text-center py-8">
                  <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">No terms documents created yet</p>
                  <p className="text-sm text-gray-500 mt-1">Create your first document to get started</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="acceptances" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Recent Acceptances</CardTitle>
              <CardDescription>
                {selectedDocument 
                  ? `Acceptances for ${selectedDocument.title} v${selectedDocument.version}`
                  : 'Recent user acceptances across all documents'
                }
              </CardDescription>
            </CardHeader>
            <CardContent>
              {acceptancesLoading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                  <p className="mt-2 text-gray-600">Loading acceptances...</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Document</TableHead>
                      <TableHead>Version</TableHead>
                      <TableHead>Accepted At</TableHead>
                      <TableHead>Method</TableHead>
                      <TableHead>IP Address</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(selectedDocument ? acceptances : stats?.recent_acceptances || []).map((acceptance) => (
                      <TableRow key={acceptance.id}>
                        <TableCell className="font-medium">{acceptance.user_id}</TableCell>
                        <TableCell>
                          <Badge variant={acceptance.document_type === 'terms_of_service' ? 'default' : 'secondary'}>
                            {acceptance.document_type === 'terms_of_service' ? 'Terms' : 'Privacy'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono">{acceptance.document_version}</TableCell>
                        <TableCell>{formatDate(acceptance.accepted_at)}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{acceptance.acceptance_method}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {acceptance.ip_address || 'N/A'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              {(!selectedDocument ? stats?.recent_acceptances || [] : acceptances).length === 0 && !acceptancesLoading && (
                <div className="text-center py-8">
                  <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">No acceptances recorded yet</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}