export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

export const runDemoStatusSequence = async (callbacks, taskId, subject = '内容') => {
  const states = [
    ['validating', 18, `正在准备${subject}演示数据`],
    ['extracting', 42, '正在读取固定示例证据'],
    ['detecting', 72, '正在模拟本地模型流程'],
    ['aggregating', 92, '正在生成隐私安全的示例报告'],
    ['completed', 100, '示例报告已生成']
  ]

  for (const [key, progress, detail] of states) {
    await wait(140)
    callbacks?.onStatus?.({
      key,
      label: detail,
      detail,
      progress,
      taskId,
      timestamp: new Date().toISOString()
    })
  }
}

export const buildDemoMediaReport = ({ taskId, mediaType, inputName }) => {
  const isVideo = mediaType === 'video'
  return {
    task_id: taskId,
    media_type: mediaType,
    verdict: isVideo ? 'ai_generated_video_suspected' : 'ai_generated',
    risk_level: 'high',
    confidence: 0.91,
    summary: '这是 GitHub Pages 固定的虚构示例报告，用于展示产品流程；不会上传文件，也没有对当前素材运行模型。',
    evidence: [
      {
        id: 'demo-model-signal',
        title: '固定模型信号示例',
        description: '展示强信号时的报告呈现；该数值是虚构演示数据，与你选择的文件无关。',
        severity: 'high',
        confidence: 0.91,
        model_score: 0.91,
        signals: ['demo_fixture_only']
      },
      {
        id: 'demo-provenance-gap',
        title: '来源信息缺口示例',
        description: '演示报告会同时展示模型信号、元数据与人工复核建议。',
        severity: 'medium',
        confidence: 0.64,
        signals: ['missing_source_context']
      }
    ],
    visualization: isVideo
      ? { key_frames: [], timeline: [], branches: {}, duration: 12 }
      : {},
    metadata: {
      filename: inputName || (isVideo ? 'demo-video.mp4' : 'demo-image.png'),
      format: isVideo ? 'mp4' : 'png',
      resolution: isVideo ? '1920 × 1080' : '1536 × 1024',
      source_hint: 'unknown',
      demo_fixture: true
    },
    models: [{
      model_id: 'zhulong-demo-fixture',
      model_version: '1.0',
      engine_type: 'static_demo',
      ai_score: 0.91,
      label: 'illustrative_only',
      latency_ms: 0
    }],
    decision: {
      quality: { status: 'experimental' },
      evidence_scores: {
        ai_evidence_strength: 0.91,
        real_evidence_strength: 0.08,
        provenance_strength: 0.12,
        conflict_level: 'low'
      }
    },
    limitations: [
      '当前页面是静态产品演示，不运行任何检测模型。',
      '选择的文件只会在浏览器本地预览，不会上传。',
      '本示例不能用于判断素材真伪。'
    ],
    created_at: new Date().toISOString()
  }
}

export const buildDemoArticleReport = ({ taskId, title }) => ({
  task_id: taskId,
  media_type: 'article',
  verdict: 'ai_style_suspected',
  risk_level: 'high',
  summary: '这是固定的虚构文字报告，用于展示分段信号与能力边界；当前文字不会发送到服务器，也未运行模型。',
  metadata: {
    title: title || '静态演示文章',
    ai_style_signal_score: 0.88,
    text_analysis_coverage: 0.92,
    demo_fixture: true
  },
  decision: { coverage: { sampled_ratio: 0.92 } },
  article: {
    text_detection: {
      model_id: 'zhulong-demo-fixture',
      model_version: '1.0',
      ai_signal_score: 0.88,
      strong_ai_segment_ratio: 1,
      analysis_coverage: 0.92,
      segments: [
        {
          segment_id: 'DEMO-01',
          index: 0,
          signal_level: 'high',
          ai_signal_score: 0.91,
          text: '这是隐私安全的虚构示例段落，用于展示高信号段落在报告中的呈现方式。'
        },
        {
          segment_id: 'DEMO-02',
          index: 1,
          signal_level: 'high',
          ai_signal_score: 0.86,
          text: '页面不会据此证明作者身份，也不会把分类器分数解释为事实概率。'
        }
      ]
    },
    sources: [],
    claims: [],
    missing_evidence: ['该结果为固定演示数据'],
    internal_consistency_issues: []
  },
  limitations: [
    '静态演示不运行中文 BERT 模型。',
    '示例分数与用户输入无关，不能用于作者身份或文章真假判断。'
  ],
  created_at: new Date().toISOString()
})
