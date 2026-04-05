/**
 * Детальная страница prompt template.
 * Табы: Шаблон, Версии, Использование.
 * Позволяет: просмотр, создание новой версии, активацию, просмотр usage.
 */

import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Tabs, Button, Tag, Space, Table, Typography, Descriptions, Modal,
  Form, Input, Select, message, Card, Collapse, Badge, Spin,
} from 'antd'
import {
  ArrowLeftOutlined, CheckCircleOutlined, PlusOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchTemplate,
  fetchVersions,
  fetchUsage,
  createNewVersion,
  activateTemplate,
  type PromptTemplate,
  type PromptTemplateUsageResponse,
  type NewVersionRequest,
  type ProfileRouteRef,
  type BlockRef,
} from '../../api/promptTemplatesApi'

const { Title, Text } = Typography
const { TextArea } = Input

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

/** Справка по template variables */
const TEMPLATE_VARIABLES = [
  { variable: '{DOC_NAME}', description: 'Название PDF-документа' },
  { variable: '{PAGE_NUM}', description: 'Номер страницы (1-based)' },
  { variable: '{BLOCK_ID}', description: 'UUID блока' },
  { variable: '{BLOCK_KIND}', description: 'Тип блока: text, stamp, image' },
  { variable: '{OPERATOR_HINT}', description: 'Подсказка оператора' },
  { variable: '{PDF_TEXT}', description: 'Текст, извлечённый из PDF (pdfplumber)' },
  { variable: '{SOURCE_NAME}', description: 'Название OCR source (OpenRouter, LM Studio)' },
  { variable: '{MODEL_NAME}', description: 'Название модели (google/gemini-2.0-flash-001)' },
]

export default function PromptTemplateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [template, setTemplate] = useState<PromptTemplate | null>(null)
  const [versions, setVersions] = useState<PromptTemplate[]>([])
  const [usage, setUsage] = useState<PromptTemplateUsageResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [newVersionModal, setNewVersionModal] = useState(false)
  const [form] = Form.useForm()

  const loadTemplate = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const t = await fetchTemplate(id)
      setTemplate(t)
    } catch (err) {
      message.error('Ошибка загрузки шаблона')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadTemplate()
  }, [loadTemplate])

  const loadVersions = useCallback(async () => {
    if (!template) return
    try {
      const resp = await fetchVersions(template.template_key)
      setVersions(resp.versions)
    } catch (err) {
      console.error(err)
    }
  }, [template])

  const loadUsage = useCallback(async () => {
    if (!id) return
    try {
      const resp = await fetchUsage(id)
      setUsage(resp)
    } catch (err) {
      console.error(err)
    }
  }, [id])

  const handleActivate = async (templateId: string) => {
    try {
      await activateTemplate(templateId)
      message.success('Версия активирована')
      loadTemplate()
      loadVersions()
    } catch (err) {
      message.error('Ошибка активации')
      console.error(err)
    }
  }

  const handleNewVersion = async () => {
    if (!template) return
    try {
      const values = await form.validateFields()
      const req: NewVersionRequest = {
        system_template: values.system_template,
        user_template: values.user_template,
        parser_strategy: values.parser_strategy,
        notes: values.notes,
      }
      const result = await createNewVersion(template.id, req)
      message.success(`Создана версия ${result.version}`)
      setNewVersionModal(false)
      navigate(`/admin/prompts/${result.id}`)
    } catch (err) {
      message.error('Ошибка создания версии')
      console.error(err)
    }
  }

  const openNewVersionModal = () => {
    if (!template) return
    form.setFieldsValue({
      system_template: template.system_template,
      user_template: template.user_template,
      parser_strategy: template.parser_strategy,
      notes: '',
    })
    setNewVersionModal(true)
  }

  // ── Колонки таблицы версий ──

  const versionColumns: ColumnsType<PromptTemplate> = [
    {
      title: 'Версия',
      dataIndex: 'version',
      key: 'version',
      width: 80,
      align: 'center',
      render: (v: number) => <Badge count={`v${v}`} style={{ backgroundColor: '#1890ff' }} />,
    },
    {
      title: 'Активна',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      align: 'center',
      render: (active: boolean) => active ? <Tag color="success">Да</Tag> : <Tag>Нет</Tag>,
    },
    {
      title: 'Parser',
      dataIndex: 'parser_strategy',
      key: 'parser_strategy',
      width: 120,
    },
    {
      title: 'Заметки',
      dataIndex: 'notes',
      key: 'notes',
      ellipsis: true,
    },
    {
      title: 'Создана',
      dataIndex: 'created_at',
      key: 'created_at',
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
            onClick={() => navigate(`/admin/prompts/${record.id}`)}
          >
            Открыть
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

  // ── Колонки usage ──

  const profileRouteColumns: ColumnsType<ProfileRouteRef> = [
    { title: 'Профиль', dataIndex: 'document_profile_name', key: 'name' },
    {
      title: 'Block Kind', dataIndex: 'block_kind', key: 'kind',
      render: (k: string) => <Tag color={BLOCK_KIND_COLORS[k]}>{k}</Tag>,
    },
  ]

  const blockColumns: ColumnsType<BlockRef> = [
    { title: 'Документ', dataIndex: 'document_title', key: 'doc' },
    { title: 'Страница', dataIndex: 'page_number', key: 'page', width: 80 },
    {
      title: 'Block Kind', dataIndex: 'block_kind', key: 'kind',
      render: (k: string) => <Tag color={BLOCK_KIND_COLORS[k]}>{k}</Tag>,
    },
  ]

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center' }}><Spin size="large" /></div>
  }

  if (!template) {
    return <div style={{ padding: 24 }}>Шаблон не найден</div>
  }

  const tabItems = [
    {
      key: 'template',
      label: 'Шаблон',
      children: (
        <div>
          {/* Справка по переменным */}
          <Collapse
            items={[{
              key: 'vars',
              label: (
                <Space>
                  <InfoCircleOutlined />
                  <span>Доступные template variables</span>
                </Space>
              ),
              children: (
                <Table
                  dataSource={TEMPLATE_VARIABLES}
                  columns={[
                    { title: 'Переменная', dataIndex: 'variable', key: 'variable', width: 180 },
                    { title: 'Описание', dataIndex: 'description', key: 'description' },
                  ]}
                  rowKey="variable"
                  pagination={false}
                  size="small"
                />
              ),
            }]}
            style={{ marginBottom: 16 }}
          />

          <Descriptions bordered column={2} size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Template Key">{template.template_key}</Descriptions.Item>
            <Descriptions.Item label="Версия">
              <Badge count={`v${template.version}`} style={{ backgroundColor: '#1890ff' }} />
            </Descriptions.Item>
            <Descriptions.Item label="Block Kind">
              <Tag color={BLOCK_KIND_COLORS[template.block_kind]}>{template.block_kind}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Source Type">
              <Tag>{template.source_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Parser Strategy">{template.parser_strategy}</Descriptions.Item>
            <Descriptions.Item label="Model Pattern">{template.model_pattern || '—'}</Descriptions.Item>
            <Descriptions.Item label="Статус" span={2}>
              {template.is_active
                ? <Tag color="success">Активен</Tag>
                : <Tag>Не активен</Tag>
              }
            </Descriptions.Item>
          </Descriptions>

          <Card title="System Template" size="small" style={{ marginBottom: 12 }}>
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              margin: 0,
              fontSize: 13,
              maxHeight: 300,
              overflow: 'auto',
            }}>
              {template.system_template}
            </pre>
          </Card>

          <Card title="User Template" size="small" style={{ marginBottom: 12 }}>
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              margin: 0,
              fontSize: 13,
              maxHeight: 300,
              overflow: 'auto',
            }}>
              {template.user_template}
            </pre>
          </Card>

          {template.output_schema_json && (
            <Card title="Output Schema JSON" size="small" style={{ marginBottom: 12 }}>
              <pre style={{
                whiteSpace: 'pre-wrap',
                margin: 0,
                fontSize: 12,
                maxHeight: 200,
                overflow: 'auto',
              }}>
                {JSON.stringify(template.output_schema_json, null, 2)}
              </pre>
            </Card>
          )}

          {template.notes && (
            <Card title="Заметки" size="small">
              <Text>{template.notes}</Text>
            </Card>
          )}
        </div>
      ),
    },
    {
      key: 'versions',
      label: 'Версии',
      children: (
        <Table<PromptTemplate>
          rowKey="id"
          columns={versionColumns}
          dataSource={versions}
          pagination={false}
          size="middle"
        />
      ),
    },
    {
      key: 'usage',
      label: 'Использование',
      children: (
        <div>
          <Title level={5}>Profile Routes</Title>
          <Table<ProfileRouteRef>
            rowKey="id"
            columns={profileRouteColumns}
            dataSource={usage?.profile_routes || []}
            pagination={false}
            size="small"
            locale={{ emptyText: 'Не используется в profile routes' }}
            style={{ marginBottom: 24 }}
          />

          <Title level={5}>Blocks с override</Title>
          <Table<BlockRef>
            rowKey="id"
            columns={blockColumns}
            dataSource={usage?.blocks || []}
            pagination={false}
            size="small"
            locale={{ emptyText: 'Нет блоков с override на этот шаблон' }}
          />
        </div>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      {/* Шапка */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/admin/prompts')}>
            Назад
          </Button>
          <Title level={3} style={{ margin: 0 }}>
            {template.template_key}
          </Title>
          <Badge count={`v${template.version}`} style={{ backgroundColor: '#1890ff' }} />
          {template.is_active
            ? <Tag color="success">Активен</Tag>
            : <Tag>Не активен</Tag>
          }
        </Space>
        <Space>
          {!template.is_active && (
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => handleActivate(template.id)}
            >
              Активировать
            </Button>
          )}
          <Button
            icon={<PlusOutlined />}
            onClick={openNewVersionModal}
          >
            Новая версия
          </Button>
        </Space>
      </div>

      {/* Табы */}
      <Tabs
        items={tabItems}
        onChange={(key) => {
          if (key === 'versions') loadVersions()
          if (key === 'usage') loadUsage()
        }}
      />

      {/* Модалка новой версии */}
      <Modal
        title={`Новая версия ${template.template_key}`}
        open={newVersionModal}
        onOk={handleNewVersion}
        onCancel={() => setNewVersionModal(false)}
        okText="Создать версию"
        cancelText="Отмена"
        width={700}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="system_template" label="System Template" rules={[{ required: true }]}>
            <TextArea rows={6} />
          </Form.Item>
          <Form.Item name="user_template" label="User Template" rules={[{ required: true }]}>
            <TextArea rows={6} />
          </Form.Item>
          <Form.Item name="parser_strategy" label="Parser Strategy">
            <Select options={PARSER_STRATEGIES} />
          </Form.Item>
          <Form.Item name="notes" label="Заметки (что изменилось)">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
