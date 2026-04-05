/**
 * Страница списка документов workspace.
 *
 * Отображает таблицу документов с навигацией в editor.
 * Включает кнопку загрузки нового PDF.
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Typography,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Upload,
  message,
  Result,
  Spin,
} from 'antd'
import {
  UploadOutlined,
  FileTextOutlined,
  ReloadOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { useWorkspace } from '../hooks/useWorkspace'
import {
  listDocuments,
  createUploadUrl,
  finalizeUpload,
  type DocumentListItem,
} from '../api/documentsApi'

const { Title } = Typography
const { Dragger } = Upload

const statusColors: Record<string, string> = {
  draft: 'default',
  uploading: 'processing',
  ready: 'success',
  processing: 'processing',
  error: 'error',
}

export default function DocumentsListPage() {
  const navigate = useNavigate()
  const { workspaceId, loading: wsLoading } = useWorkspace()
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const pageSize = 20

  // Upload modal
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [form] = Form.useForm()

  const loadDocuments = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const result = await listDocuments(workspaceId, pageSize, (page - 1) * pageSize)
      setDocuments(result.documents)
      setTotal(result.total)
    } catch (err) {
      message.error('Ошибка загрузки списка документов')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [workspaceId, page])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const handleUpload = async (values: { title: string; file: { file: File } }) => {
    if (!workspaceId) return

    const file = values.file?.file
    if (!file || !(file instanceof File)) {
      message.error('Выберите PDF файл')
      return
    }

    setUploading(true)
    try {
      // 1. Получить presigned URL
      const { documentId, uploadUrl } = await createUploadUrl(workspaceId, values.title)

      // 2. Загрузить PDF напрямую в R2
      const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': 'application/pdf' },
      })

      if (!uploadResponse.ok) {
        throw new Error(`Ошибка загрузки в R2: ${uploadResponse.status}`)
      }

      // 3. Финализировать
      await finalizeUpload(documentId)

      message.success('Документ загружен')
      setUploadOpen(false)
      form.resetFields()

      // Перейти в editor
      navigate(`/documents/${documentId}`)
    } catch (err) {
      message.error(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setUploading(false)
    }
  }

  const columns: ColumnsType<DocumentListItem> = [
    {
      title: 'Название',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, record) => (
        <a onClick={() => navigate(`/documents/${record.id}`)}>
          <FileTextOutlined style={{ marginRight: 8 }} />
          {title}
        </a>
      ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: 'Страниц',
      dataIndex: 'pageCount',
      key: 'pageCount',
      width: 100,
      align: 'center',
    },
    {
      title: 'Создан',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (val: string) => new Date(val).toLocaleString('ru-RU'),
    },
    {
      title: 'Обновлён',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 180,
      render: (val: string) => new Date(val).toLocaleString('ru-RU'),
    },
    {
      title: '',
      key: 'actions',
      width: 100,
      render: (_: unknown, record) => (
        <Button type="link" onClick={() => navigate(`/documents/${record.id}`)}>
          Открыть
        </Button>
      ),
    },
  ]

  if (wsLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }}>
        <Spin size="large" tip="Загрузка workspace..." />
      </div>
    )
  }

  if (!workspaceId) {
    return <Result status="warning" title="Workspace не найден" subTitle="Обратитесь к администратору для получения доступа" />
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Документы</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadDocuments} loading={loading}>
            Обновить
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
            Загрузить PDF
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={documents}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: setPage,
          showSizeChanger: false,
          showTotal: (t) => `Всего: ${t}`,
        }}
      />

      <Modal
        title="Загрузка документа"
        open={uploadOpen}
        onCancel={() => { if (!uploading) setUploadOpen(false) }}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleUpload}>
          <Form.Item
            name="title"
            label="Название документа"
            rules={[{ required: true, message: 'Введите название' }]}
          >
            <Input placeholder="Например: Договор №123" />
          </Form.Item>

          <Form.Item
            name="file"
            label="PDF файл"
            rules={[{ required: true, message: 'Выберите файл' }]}
          >
            <Dragger
              accept=".pdf"
              maxCount={1}
              beforeUpload={() => false}
              style={{ padding: '20px 0' }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">Перетащите PDF файл или нажмите для выбора</p>
            </Dragger>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={uploading} block>
              Загрузить
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
