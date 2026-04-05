/**
 * Страница списка prompt templates с фильтрами.
 * Позволяет: просмотр, создание, клонирование, активацию шаблонов.
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Select, Space, Tag, Input, Modal, Form,
  message, Typography, Switch, Card,
} from 'antd'
import {
  PlusOutlined, CopyOutlined, CheckCircleOutlined, EyeOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchTemplates,
  createTemplate,
  cloneTemplate,
  activateTemplate,
  type PromptTemplate,
  type TemplateFilters,
  type CreateTemplateRequest,
} from '../../api/promptTemplatesApi'

const { Title } = Typography

const BLOCK_KINDS = [
  { value: 'text', label: 'Text' },
  { value: 'stamp', label: 'Stamp' },
  { value: 'image', label: 'Image' },
]

const SOURCE_TYPES = [
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'lmstudio', label: 'LM Studio' },
]

const PARSER_STRATEGIES = [
  { value: 'plain_text', label: 'Plain Text' },
  { value: 'stamp_json', label: 'Stamp JSON' },
  { value: 'image_json', label: 'Image JSON' },
  { value: 'html_fragment', label: 'HTML Fragment' },
]

const BLOCK_KIND_COLORS: Record<string, string> = {
  text: 'blue',
  stamp: 'orange',
  image: 'green',
}

export default function PromptTemplatesPage() {
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [cloneModalOpen, setCloneModalOpen] = useState(false)
  const [cloneSourceId, setCloneSourceId] = useState<string | null>(null)
  const [createForm] = Form.useForm()
  const [cloneForm] = Form.useForm()

  // Фильтры
  const [filters, setFilters] = useState<TemplateFilters>({
    limit: 20,
    offset: 0,
  })

  const loadTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetchTemplates(filters)
      setTemplates(resp.templates)
      setTotal(resp.meta.total)
    } catch (err) {
      message.error('Ошибка загрузки шаблонов')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  const handleFilterChange = (key: keyof TemplateFilters, value: unknown) => {
    setFilters(prev => ({
      ...prev,
      [key]: value || undefined,
      offset: 0,
    }))
  }

  const handleActivate = async (id: string) => {
    try {
      await activateTemplate(id)
      message.success('Шаблон активирован')
      loadTemplates()
    } catch (err) {
      message.error('Ошибка активации')
      console.error(err)
    }
  }

  const handleClone = (id: string) => {
    setCloneSourceId(id)
    cloneForm.resetFields()
    setCloneModalOpen(true)
  }

  const handleCloneSubmit = async () => {
    if (!cloneSourceId) return
    try {
      const values = await cloneForm.validateFields()
      const result = await cloneTemplate(cloneSourceId, values.new_template_key)
      message.success(`Шаблон клонирован: ${result.template_key}`)
      setCloneModalOpen(false)
      loadTemplates()
    } catch (err) {
      message.error('Ошибка клонирования')
      console.error(err)
    }
  }

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      const req: CreateTemplateRequest = {
        template_key: values.template_key,
        block_kind: values.block_kind,
        source_type: values.source_type,
        system_template: values.system_template,
        user_template: values.user_template,
        parser_strategy: values.parser_strategy || 'plain_text',
        notes: values.notes,
      }
      const result = await createTemplate(req)
      message.success(`Шаблон создан: ${result.template_key}`)
      setCreateModalOpen(false)
      createForm.resetFields()
      loadTemplates()
    } catch (err) {
      message.error('Ошибка создания шаблона')
      console.error(err)
    }
  }

  const columns: ColumnsType<PromptTemplate> = [
    {
      title: 'Template Key',
      dataIndex: 'template_key',
      key: 'template_key',
      render: (text: string, record: PromptTemplate) => (
        <a onClick={() => navigate(`/admin/prompts/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: 'Версия',
      dataIndex: 'version',
      key: 'version',
      width: 80,
      align: 'center',
    },
    {
      title: 'Block Kind',
      dataIndex: 'block_kind',
      key: 'block_kind',
      width: 100,
      render: (kind: string) => (
        <Tag color={BLOCK_KIND_COLORS[kind] || 'default'}>{kind}</Tag>
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 110,
      render: (s: string) => (
        <Tag>{s}</Tag>
      ),
    },
    {
      title: 'Parser',
      dataIndex: 'parser_strategy',
      key: 'parser_strategy',
      width: 120,
    },
    {
      title: 'Активен',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      align: 'center',
      render: (active: boolean) => (
        active
          ? <Tag color="success">Да</Tag>
          : <Tag>Нет</Tag>
      ),
    },
    {
      title: 'Обновлён',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (d: string) => new Date(d).toLocaleString('ru-RU'),
    },
    {
      title: 'Действия',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: PromptTemplate) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/admin/prompts/${record.id}`)}
          >
            Открыть
          </Button>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => handleClone(record.id)}
          >
            Клон
          </Button>
          {!record.is_active && (
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => handleActivate(record.id)}
            >
              Активировать
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>Prompt Templates</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            createForm.resetFields()
            setCreateModalOpen(true)
          }}
        >
          Создать шаблон
        </Button>
      </div>

      {/* Фильтры */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="Block Kind"
            allowClear
            style={{ width: 140 }}
            options={BLOCK_KINDS}
            onChange={v => handleFilterChange('block_kind', v)}
          />
          <Select
            placeholder="Source Type"
            allowClear
            style={{ width: 140 }}
            options={SOURCE_TYPES}
            onChange={v => handleFilterChange('source_type', v)}
          />
          <Input
            placeholder="Model pattern"
            allowClear
            style={{ width: 180 }}
            onChange={e => handleFilterChange('model_pattern', e.target.value)}
          />
          <Space>
            <span>Только активные:</span>
            <Switch
              onChange={checked => handleFilterChange('is_active', checked || undefined)}
            />
          </Space>
        </Space>
      </Card>

      {/* Таблица */}
      <Table<PromptTemplate>
        rowKey="id"
        columns={columns}
        dataSource={templates}
        loading={loading}
        pagination={{
          total,
          pageSize: filters.limit || 20,
          current: Math.floor((filters.offset || 0) / (filters.limit || 20)) + 1,
          onChange: (page, pageSize) => {
            setFilters(prev => ({
              ...prev,
              offset: (page - 1) * pageSize,
              limit: pageSize,
            }))
          },
          showSizeChanger: true,
          showTotal: (t) => `Всего: ${t}`,
        }}
        size="middle"
      />

      {/* Модалка создания */}
      <Modal
        title="Создать новый prompt template"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => setCreateModalOpen(false)}
        okText="Создать"
        cancelText="Отмена"
        width={700}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="template_key" label="Template Key" rules={[{ required: true }]}>
            <Input placeholder="my_custom_prompt" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="block_kind" label="Block Kind" rules={[{ required: true }]}>
              <Select options={BLOCK_KINDS} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="source_type" label="Source Type" rules={[{ required: true }]}>
              <Select options={SOURCE_TYPES} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="parser_strategy" label="Parser Strategy">
              <Select options={PARSER_STRATEGIES} style={{ width: 160 }} defaultValue="plain_text" />
            </Form.Item>
          </Space>
          <Form.Item name="system_template" label="System Template" rules={[{ required: true }]}>
            <Input.TextArea rows={4} placeholder="Ты — OCR-система..." />
          </Form.Item>
          <Form.Item name="user_template" label="User Template" rules={[{ required: true }]}>
            <Input.TextArea rows={4} placeholder="Распознай текст на изображении..." />
          </Form.Item>
          <Form.Item name="notes" label="Заметки">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Модалка клонирования */}
      <Modal
        title="Клонировать шаблон"
        open={cloneModalOpen}
        onOk={handleCloneSubmit}
        onCancel={() => setCloneModalOpen(false)}
        okText="Клонировать"
        cancelText="Отмена"
      >
        <Form form={cloneForm} layout="vertical">
          <Form.Item name="new_template_key" label="Новый Template Key">
            <Input placeholder="Оставьте пустым для автоматического имени" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
