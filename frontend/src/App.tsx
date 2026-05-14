import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Flex,
  Form,
  Input,
  Layout,
  Progress,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
  message,
  Modal,
} from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  DeleteOutlined,
  DownloadOutlined,
  FileMarkdownOutlined,
  LockOutlined,
  LogoutOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import axios from 'axios';

axios.defaults.timeout = 30000;

const { Header, Content, Footer } = Layout;
const { Title, Text, Paragraph } = Typography;

type JobStatus = 'queued' | 'running' | 'complete' | 'failed';

interface Job {
  id: string;
  original_filename: string;
  document_stem: string;
  status: JobStatus;
  stage: string;
  progress: number;
  created_at: number;
  updated_at: number;
  error?: string | null;
}

interface AuthStatus {
  authenticated: boolean;
  token_required: boolean;
  loopback_only: boolean;
}

const statusColor: Record<JobStatus, string> = {
  queued: 'default',
  running: 'processing',
  complete: 'success',
  failed: 'error',
};

function formatTime(value: number) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value * 1000));
}

function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [token, setToken] = useState('');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [archiveFormat, setArchiveFormat] = useState<'zip' | 'tar.gz'>('zip');
  const [uploading, setUploading] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? jobs[0],
    [jobs, selectedJobId],
  );

  const loadAuth = async () => {
    const res = await axios.get<AuthStatus>('/auth/status');
    setAuth(res.data);
  };

  const loadJobs = async () => {
    if (!auth?.authenticated) return;
    setLoadingJobs(true);
    try {
      const res = await axios.get<{ jobs: Job[] }>('/jobs');
      setJobs(res.data.jobs);
      if (!selectedJobId && res.data.jobs.length > 0) {
        setSelectedJobId(res.data.jobs[0].id);
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        setAuth((current) => current ? { ...current, authenticated: false } : current);
      }
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    loadAuth().catch(() => {
      setAuth({ authenticated: false, token_required: true, loopback_only: false });
    });
  }, []);

  useEffect(() => {
    if (!auth?.authenticated) return;
    loadJobs();
    const timer = window.setInterval(loadJobs, 2500);
    return () => window.clearInterval(timer);
  }, [auth?.authenticated]);

  const signIn = async () => {
    const body = new FormData();
    body.append('token', token);
    try {
      await axios.post('/auth', body);
      await loadAuth();
      message.success('Signed in');
    } catch {
      message.error('Invalid private access token');
    }
  };

  const logout = async () => {
    await axios.post('/auth/logout');
    setJobs([]);
    setSelectedJobId(null);
    await loadAuth();
  };

  const uploadPdf = async () => {
    const file = fileList[0]?.originFileObj;
    if (!file) {
      message.warning('Choose a PDF first');
      return;
    }

    const body = new FormData();
    body.append('file', file);
    setUploading(true);
    try {
      const res = await axios.post<Job>('/jobs', body);
      setSelectedJobId(res.data.id);
      setFileList([]);
      await loadJobs();
      message.success('Conversion job started');
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
      const timeoutMessage = axios.isAxiosError(error) && error.code === 'ECONNABORTED'
        ? 'Upload timed out before the server created a job. Check that the private Marker server is still running.'
        : null;
      const networkMessage = axios.isAxiosError(error) && !error.response
        ? 'Cannot reach the private Marker server. Check that it is running on this host and port.'
        : null;
      message.error(detail || timeoutMessage || networkMessage || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const deleteJob = async (job: Job) => {
    Modal.confirm({
      title: 'Delete conversion job?',
      content: `This removes ${job.original_filename} and its generated archives from this server.`,
      okText: 'Delete',
      okButtonProps: { danger: true },
      async onOk() {
        try {
          await axios.delete(`/jobs/${job.id}`);
          setSelectedJobId((current) => current === job.id ? null : current);
          await loadJobs();
          message.success('Job deleted');
        } catch (error) {
          const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
          message.error(detail || 'Could not delete job');
        }
      },
    });
  };

  const signedIn = !!auth?.authenticated;

  return (
    <ConfigProvider
      theme={{
        token: {
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif",
          colorPrimary: '#0071e3',
          borderRadius: 12,
          colorBgContainer: '#ffffff',
          colorBgLayout: '#f5f5f7',
        },
        components: {
          Layout: {
            headerBg: 'rgba(255, 255, 255, 0.8)',
            headerColor: '#1d1d1f',
          },
          Card: {
            boxShadowTertiary: '0 4px 12px rgba(0,0,0,0.05)',
          },
        },
      }}
    >
      <Layout className="marker-shell">
        <Header className="marker-header">
          <Flex align="center" gap={12}>
            <FileMarkdownOutlined style={{ fontSize: 24, color: '#0071e3' }} />
            <div>
              <Title level={4} style={{ margin: 0 }}>Private Marker Converter</Title>
              <Text type="secondary">Personal, non-commercial PDF to Markdown conversion</Text>
            </div>
          </Flex>
          <Space>
            {signedIn ? (
              <>
                <Tag color="success">Signed in</Tag>
                <Button icon={<ReloadOutlined />} onClick={loadJobs} loading={loadingJobs}>Refresh</Button>
                <Button icon={<LogoutOutlined />} onClick={logout}>Sign out</Button>
              </>
            ) : (
              <Tag icon={<LockOutlined />} color="warning">Private access required</Tag>
            )}
          </Space>
        </Header>

        <Content className="marker-content">
          {!signedIn ? (
            <Card>
              <div className="marker-card-title">
                <Title level={3}>Sign in</Title>
                <Paragraph type="secondary">
                  Enter the private access token configured with <Text code>MARKER_WEB_TOKEN</Text>.
                  After sign-in, this header will show the current authenticated state.
                </Paragraph>
              </div>
              {auth?.loopback_only && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="Loopback-only mode"
                  description="No MARKER_WEB_TOKEN is configured. The server allows only local loopback access."
                />
              )}
              <Form layout="vertical" onFinish={signIn}>
                <Form.Item label="Private access token">
                  <Input.Password
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    placeholder="Private token"
                  />
                </Form.Item>
                <Button type="primary" htmlType="submit">Sign in</Button>
              </Form>
            </Card>
          ) : (
            <div className="marker-grid">
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Card>
                  <div className="marker-card-title">
                    <Title level={3}>Convert PDF</Title>
                    <Paragraph type="secondary">
                      Uploaded files and generated archives stay on this private server until you delete the job.
                    </Paragraph>
                  </div>
                  <Upload
                    accept="application/pdf,.pdf"
                    maxCount={1}
                    fileList={fileList}
                    beforeUpload={() => false}
                    onChange={({ fileList: nextList }) => setFileList(nextList)}
                  >
                    <Button icon={<UploadOutlined />}>Choose PDF</Button>
                  </Upload>
                  <Flex align="center" gap={12} style={{ marginTop: 16 }} wrap>
                    <Select
                      value={archiveFormat}
                      style={{ width: 140 }}
                      onChange={setArchiveFormat}
                      options={[
                        { value: 'zip', label: '.zip' },
                        { value: 'tar.gz', label: '.tar.gz' },
                      ]}
                    />
                    <Button type="primary" onClick={uploadPdf} loading={uploading}>
                      Start conversion
                    </Button>
                  </Flex>
                </Card>

                <Card>
                  <Flex align="center" justify="space-between" gap={12} className="marker-card-title">
                    <Title level={3} style={{ margin: 0 }}>Selected job</Title>
                    {selectedJob && <Tag color={statusColor[selectedJob.status]}>{selectedJob.status}</Tag>}
                  </Flex>
                  {!selectedJob ? (
                    <Alert type="info" showIcon message="No conversion jobs yet" />
                  ) : (
                    <Space direction="vertical" size={14} style={{ width: '100%' }}>
                      <div>
                        <Text strong>{selectedJob.original_filename}</Text>
                        <br />
                        <Text type="secondary">Created {formatTime(selectedJob.created_at)}</Text>
                      </div>
                      <Progress percent={selectedJob.progress} status={selectedJob.status === 'failed' ? 'exception' : undefined} />
                      <Text type={selectedJob.status === 'failed' ? 'danger' : 'secondary'}>
                        {selectedJob.error || selectedJob.stage}
                      </Text>
                      {selectedJob.status === 'complete' && (
                        <div className="downloads">
                          <Button
                            type="primary"
                            icon={<DownloadOutlined />}
                            href={`/jobs/${selectedJob.id}/download?format=${archiveFormat}`}
                          >
                            Download {archiveFormat}
                          </Button>
                          <Button href={`/jobs/${selectedJob.id}/download?format=zip`}>.zip</Button>
                          <Button href={`/jobs/${selectedJob.id}/download?format=tar.gz`}>.tar.gz</Button>
                          <Button danger icon={<DeleteOutlined />} onClick={() => deleteJob(selectedJob)}>
                            Delete
                          </Button>
                        </div>
                      )}
                      {selectedJob.status === 'failed' && (
                        <Button danger icon={<DeleteOutlined />} onClick={() => deleteJob(selectedJob)}>
                          Delete failed job
                        </Button>
                      )}
                    </Space>
                  )}
                </Card>
              </Space>

              <Card>
                <Flex align="center" justify="space-between" className="marker-card-title">
                  <Title level={3} style={{ margin: 0 }}>Jobs</Title>
                  <Text type="secondary">{jobs.length} retained</Text>
                </Flex>
                {jobs.length === 0 ? (
                  <Alert type="info" showIcon message="No retained jobs" />
                ) : (
                  jobs.map((job) => (
                    <button
                      key={job.id}
                      className={`job-row ${selectedJob?.id === job.id ? 'is-selected' : ''}`}
                      onClick={() => setSelectedJobId(job.id)}
                    >
                      <div className="job-row-name">
                        <Text strong ellipsis>{job.original_filename}</Text>
                        <Tag color={statusColor[job.status]}>{job.status}</Tag>
                      </div>
                      <Progress percent={job.progress} size="small" showInfo={false} />
                      <Text type="secondary">{job.stage} · {formatTime(job.updated_at)}</Text>
                    </button>
                  ))
                )}
              </Card>
            </div>
          )}
        </Content>

        <Footer style={{ textAlign: 'center', color: '#6e6e73' }}>
          Powered by <a href="https://github.com/VikParuchuri/marker">Marker</a>. This private tool is intended only for the maintainer&apos;s personal, non-commercial document conversion use.
        </Footer>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
