import sqlite3
import json
import datetime
import os
import re
from collections import Counter

DB_FILE = 'tita_logs.db'
OUTPUT_HTML = 'daily_report_dashboard.html'

html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>市场销售日报洞察大屏</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js"></script>
    <style>
        body { background-color: #f3f4f6; color: #1f2937; font-family: 'Inter', system-ui, sans-serif; }
        .card { background: white; border-radius: 0.75rem; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1); padding: 1.5rem; transition: all 0.2s; }
        .card:hover { box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }
        .tag { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; }
        .tag-risk { background-color: #fef2f2; color: #991b1b; }
        .tag-opp { background-color: #f0fdf4; color: #166534; }
        .tag-info { background-color: #eff6ff; color: #1e40af; }
        .clickable { cursor: pointer; }
        [v-cloak] { display: none; }
        
        /* Masonry-like grid for intelligence */
        .masonry-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
    </style>
</head>
<body>
    <div id="app" v-cloak class="min-h-screen flex flex-col">
        <!-- 顶部导航 -->
        <header class="bg-white shadow-sm z-10 sticky top-0">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between h-16">
                    <div class="flex">
                        <div class="flex-shrink-0 flex items-center cursor-pointer" @click="currentView = 'dashboard'">
                            <h1 class="text-xl font-bold text-gray-900 flex items-center gap-2">
                                📊 市场销售日报洞察 <span class="text-xs text-gray-400 font-normal border border-gray-200 rounded px-1">{{ yesterdayDate }}</span>
                            </h1>
                        </div>
                        <div class="hidden sm:ml-6 sm:flex sm:space-x-8">
                            <a href="#" @click="currentView = 'dashboard'" :class="currentView === 'dashboard' ? 'border-indigo-500 text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-700'" class="border-b-2 px-1 pt-1 inline-flex items-center text-sm font-medium transition-colors">总览看板</a>
                            <a href="#" @click="currentView = 'intelligence'" :class="currentView === 'intelligence' ? 'border-indigo-500 text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-700'" class="border-b-2 px-1 pt-1 inline-flex items-center text-sm font-medium transition-colors">情报透视</a>
                            <a href="#" @click="currentView = 'explorer'" :class="currentView === 'explorer' ? 'border-indigo-500 text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-700'" class="border-b-2 px-1 pt-1 inline-flex items-center text-sm font-medium transition-colors">数据检索</a>
                        </div>
                    </div>
                    <div class="flex items-center space-x-4">
                        <span class="text-sm text-gray-500">更新时间: {{ generatedAt }}</span>
                        <div class="flex items-center gap-2">
                            <button @click="manualFetch" :disabled="isFetching" 
                                    class="px-3 py-1.5 text-sm font-medium rounded-md transition-all"
                                    :class="isFetching ? 'bg-gray-200 text-gray-500 cursor-not-allowed' : 'bg-indigo-600 text-white hover:bg-indigo-700'">
                                <span v-if="isFetching">⏳ {{ fetchProgress.current }}/{{ fetchProgress.total || '?' }}</span>
                                <span v-else>🔄 手动拉取</span>
                            </button>
                            <span v-if="isFetching" class="text-xs text-gray-500 max-w-xs truncate">{{ fetchProgress.message }}</span>
                        </div>
                        <button @click="resetFilters" class="text-sm text-indigo-600 hover:text-indigo-900 font-medium">重置筛选</button>
                    </div>
                </div>
            </div>
            
            <!-- 全局筛选反馈 (当有筛选时显示) -->
            <div v-if="filters.department || filters.search" class="bg-indigo-50 border-t border-indigo-100">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center space-x-2 text-xs text-indigo-700">
                    <span class="font-bold">当前筛选:</span>
                    <span v-if="filters.department" class="bg-indigo-100 px-2 py-0.5 rounded">部门: {{ filters.department }}</span>
                    <span v-if="filters.search" class="bg-indigo-100 px-2 py-0.5 rounded">搜索: {{ filters.search }}</span>
                    <button @click="resetFilters" class="text-indigo-500 hover:text-indigo-800 ml-2">✕ 清除</button>
                </div>
            </div>
        </header>

        <!-- 主内容区 -->
        <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
            
            <!-- 1. 总览看板 -->
            <div v-show="currentView === 'dashboard'" class="space-y-6">
                 <!-- 智能一句话总结 -->
                <div class="card bg-gradient-to-r from-indigo-500 to-purple-600 text-white border-none shadow-lg">
                    <div class="flex items-start gap-4">
                        <div class="text-3xl">🤖</div>
                        <div>
                            <h3 class="text-lg font-bold opacity-90 mb-1">AI 每日综述</h3>
                            <p class="text-sm md:text-base leading-relaxed font-light opacity-95">
                                <span v-if="summarySentence">{{ summarySentence }}</span>
                                <span v-else>今日共收集 <b>{{ kpi.peopleCount }}</b> 人的日报，覆盖 <b>{{ kpi.schoolCount }}</b> 所学校。重点识别到 <b>{{ kpi.riskCount }}</b> 项风险与 <b>{{ kpi.oppCount }}</b> 个潜在商机，建议优先关注 <span class="underline cursor-pointer" @click="jumpToIntelligence('risk')">风险排查</span> 板块。</span>
                            </p>
                        </div>
                    </div>
                </div>

                <!-- KPI 卡片 (可点击) -->
                <div class="grid grid-cols-1 gap-5 sm:grid-cols-4">
                    <div class="card clickable hover:border-indigo-300 border border-transparent" @click="currentView = 'explorer'">
                        <dt class="text-sm font-medium text-gray-500 truncate">日报提交人数</dt>
                        <dd class="mt-1 text-3xl font-semibold text-gray-900">{{ kpi.peopleCount }}</dd>
                    </div>
                    <div class="card clickable hover:border-indigo-300 border border-transparent" @click="filterByKeyword('学校')">
                        <dt class="text-sm font-medium text-gray-500 truncate">提及学校数</dt>
                        <dd class="mt-1 text-3xl font-semibold text-gray-900">{{ kpi.schoolCount }}</dd>
                    </div>
                    <div class="card clickable border-l-4 border-red-500 hover:bg-red-50" @click="jumpToIntelligence('risk')">
                        <dt class="text-sm font-medium text-gray-500 truncate">风险预警 (投诉/阻碍)</dt>
                        <dd class="mt-1 text-3xl font-semibold text-red-600">{{ kpi.riskCount }}</dd>
                        <div class="text-xs text-red-400 mt-1">点击查看详情 ></div>
                    </div>
                    <div class="card clickable border-l-4 border-green-500 hover:bg-green-50" @click="jumpToIntelligence('opp')">
                        <dt class="text-sm font-medium text-gray-500 truncate">高潜机会 (新需求)</dt>
                        <dd class="mt-1 text-3xl font-semibold text-green-600">{{ kpi.oppCount }}</dd>
                        <div class="text-xs text-green-400 mt-1">点击查看详情 ></div>
                    </div>
                </div>

                <!-- 图表区 -->
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                     <!-- 词云 -->
                    <div class="card h-96 col-span-1 lg:col-span-2 flex flex-col">
                        <h3 class="text-gray-700 font-bold mb-4">🔥 热点关键词云</h3>
                        <div id="chart-wordcloud" class="flex-1 w-full h-full"></div>
                    </div>
                    <!-- 维度分布 -->
                    <div class="card h-96 col-span-1 flex flex-col">
                        <h3 class="text-gray-700 font-bold mb-4">情报维度分布</h3>
                        <div id="chart-dimensions" class="flex-1 w-full h-full"></div>
                    </div>
                </div>
            </div>

            <!-- 2. 情报透视 (Grid View) -->
            <div v-show="currentView === 'intelligence'" class="space-y-6">
                <!-- Tabs -->
                <div class="flex space-x-2 p-1 bg-gray-200 rounded-lg inline-flex">
                    <button @click="intelTab = 'risk'" :class="intelTab === 'risk' ? 'bg-white text-red-700 shadow' : 'text-gray-600 hover:text-gray-900'" class="px-4 py-2 rounded-md text-sm font-medium transition-all">
                        ⚠️ 风险排查 <span class="ml-1 bg-red-100 text-red-800 px-1.5 py-0.5 rounded-full text-xs" v-if="intelCounts.risk">{{ intelCounts.risk }}</span>
                    </button>
                    <button @click="intelTab = 'opp'" :class="intelTab === 'opp' ? 'bg-white text-green-700 shadow' : 'text-gray-600 hover:text-gray-900'" class="px-4 py-2 rounded-md text-sm font-medium transition-all">
                        💡 机会与需求 <span class="ml-1 bg-green-100 text-green-800 px-1.5 py-0.5 rounded-full text-xs" v-if="intelCounts.opp">{{ intelCounts.opp }}</span>
                    </button>
                    <button @click="intelTab = 'market'" :class="intelTab === 'market' ? 'bg-white text-blue-700 shadow' : 'text-gray-600 hover:text-gray-900'" class="px-4 py-2 rounded-md text-sm font-medium transition-all">
                        ⚔️ 竞争与画像 <span class="ml-1 bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded-full text-xs" v-if="intelCounts.market">{{ intelCounts.market }}</span>
                    </button>
                </div>

                <!-- Grid View -->
                <div class="masonry-grid">
                    <div v-for="(item, index) in filteredIntelItems" :key="index" 
                         class="card flex flex-col justify-between hover:ring-2 ring-indigo-500 ring-opacity-50 relative overflow-hidden group">
                        
                        <!-- Decoration Bar -->
                        <div class="absolute top-0 left-0 w-1.5 h-full" :class="{
                            'bg-red-500': intelTab === 'risk',
                            'bg-green-500': intelTab === 'opp',
                            'bg-blue-500': intelTab === 'market'
                        }"></div>

                        <div class="pl-3">
                            <div class="flex justify-between items-start mb-2">
                                <span class="text-xs font-semibold px-2 py-1 rounded bg-gray-100 text-gray-600">{{ item.dimension }}</span>
                                <span class="text-xs text-gray-400">{{ item.date.substring(5) }}</span>
                            </div>
                            <h4 class="text-gray-900 font-medium mb-2 text-sm leading-relaxed">{{ item.content }}</h4>
                            
                            <div class="mt-4 pt-4 border-t border-gray-100 flex justify-between items-center text-xs">
                                <div class="flex items-center gap-2">
                                    <span class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center font-bold">{{ item.userName[0] }}</span>
                                    <span class="text-gray-600">{{ item.userName }}</span>
                                </div>
                                <button @click="openDetailLog(item.log)" class="text-indigo-600 hover:text-indigo-800 font-medium opacity-0 group-hover:opacity-100 transition-opacity">查看原文</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div v-if="filteredIntelItems.length === 0" class="text-center py-20">
                    <div class="text-6xl mb-4">🍃</div>
                    <p class="text-gray-500">该分类下今日暂无相关情报。</p>
                </div>
            </div>

            <!-- 3. 数据检索 (列表) -->
             <div v-show="currentView === 'explorer'" class="space-y-4">
                 <!-- 内部搜索栏 (如果Header不够显眼) -->
                 <div class="flex gap-4 mb-4">
                     <select v-model="filters.department" class="block w-32 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm p-2 border">
                         <option value="">所有部门</option>
                         <option v-for="dept in uniqueDepartments" :key="dept" :value="dept">{{ dept }}</option>
                     </select>
                     <input v-model="filters.search" type="text" placeholder="在此通过关键词检索..." class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm p-2 border">
                 </div>

                 <div class="card overflow-hidden p-0">
                     <table class="min-w-full divide-y divide-gray-200">
                         <thead class="bg-gray-50">
                             <tr>
                                 <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">人员</th>
                                 <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-20">部门</th>
                                 <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">智能标签 & 摘要</th>
                                 <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">操作</th>
                             </tr>
                         </thead>
                         <tbody class="bg-white divide-y divide-gray-200">
                             <tr v-for="log in filteredLogs" :key="log.feed_id" class="hover:bg-gray-50 transition-colors">
                                 <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ log.user_name }}</td>
                                 <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ log.department }}</td>
                                 <td class="px-6 py-4 text-sm text-gray-500">
                                     <div class="flex flex-wrap gap-1 mb-1">
                                         <span v-if="hasTag(log, '投诉')" class="tag tag-risk">投诉</span>
                                         <span v-if="hasTag(log, '阻碍')" class="tag tag-risk">阻碍</span>
                                         <span v-if="hasTag(log, '画像')" class="tag tag-info">学校画像</span>
                                         <span v-if="hasTag(log, '机会')" class="tag tag-opp">机会</span>
                                     </div>
                                     <div class="text-xs text-gray-500 truncate max-w-xl">{{ getDigest(log) }}</div>
                                 </td>
                                 <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                     <button @click="openDetail(log)" class="text-indigo-600 hover:text-indigo-900">详情</button>
                                 </td>
                             </tr>
                         </tbody>
                     </table>
                 </div>
             </div>

        </main>

        <!-- 详情弹窗 -->
        <div v-if="selectedLog" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center p-4 z-50 backdrop-blur-sm" @click.self="selectedLog = null">
            <div class="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
                <div class="p-6 border-b border-gray-200 flex justify-between items-center bg-gray-50">
                    <div>
                        <h2 class="text-xl font-bold text-gray-900">{{ selectedLog.user_name }} 的工作日报</h2>
                        <p class="text-sm text-gray-500">{{ selectedLog.log_date }} | {{ selectedLog.department }}</p>
                    </div>
                    <button @click="selectedLog = null" class="text-gray-400 hover:text-gray-600 bg-white rounded-full p-1 hover:bg-gray-100 transition-colors">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                </div>
                
                <div class="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
                    <!-- 左侧：AI 分析 -->
                    <div class="space-y-4">
                         <div class="flex items-center gap-2 mb-2">
                             <span class="text-lg">🧠</span> 
                             <h3 class="font-bold text-gray-800">AI 智能洞察</h3>
                         </div>
                         <div v-for="(val, key) in parseAnalysis(selectedLog.analysis_json)" :key="key" 
                              v-show="val && val.length > 2 && val !== '无'"
                              class="bg-indigo-50 p-3 rounded-lg border border-indigo-100">
                             <span class="font-bold text-indigo-800 text-xs uppercase tracking-wide block mb-1">{{ key }}</span>
                             <p class="text-gray-800 text-sm leading-relaxed">{{ val }}</p>
                         </div>
                    </div>

                    <!-- 右侧：原文 -->
                    <div class="space-y-4">
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-lg">📄</span> 
                            <h3 class="font-bold text-gray-800">日志原文</h3>
                        </div>
                        <div class="bg-gray-50 p-4 rounded-lg border border-gray-200 h-full overflow-y-auto max-h-[600px]">
                            <pre class="whitespace-pre-wrap text-sm text-gray-600 font-mono leading-relaxed">{{ selectedLog.content }}</pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const RAW_DATA = {{DATA_PLACEHOLDER}};
        
        const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

        createApp({
            setup() {
                const logs = ref(RAW_DATA.logs);
                const generatedAt = RAW_DATA.generated_at;
                const yesterdayDate = RAW_DATA.yesterday_date || 'Unknown';
                const wordCloudData = RAW_DATA.word_cloud_data || [];
                
                const currentView = ref('dashboard');
                const intelTab = ref('risk');
                const selectedLog = ref(null);
                
                const filters = ref({ dateRange: 'yesterday', department: '', search: '' });

                // Logic
                const parseAnalysis = (jsonStr) => { try { return JSON.parse(jsonStr); } catch (e) { return {}; } };

                const uniqueDepartments = computed(() => [...new Set(logs.value.map(l => l.department))].filter(Boolean));

                const filteredLogs = computed(() => {
                    return logs.value.filter(log => {
                        if (filters.value.dateRange === 'yesterday' && log.log_date !== yesterdayDate) return false;
                        if (filters.value.department && log.department !== filters.value.department) return false;
                        if (filters.value.search) {
                            const q = filters.value.search.toLowerCase();
                            return (log.content + log.user_name).toLowerCase().includes(q);
                        }
                        return true;
                    });
                });

                const targetDims = {
                    'risk': ['用户投诉', '销售流程阻碍点', '系统性与运营类问题', '合作伙伴协同状态（移动公司）'],
                    'opp': ['场景化需求与痛点', '新业务与新模式反馈', '用户需求', '业务发展进展'],
                    'market': ['竞争动态与替代风险', '学校画像信息（规模/关键人/信息化水平/预算）', '客户关系深度（决策链）']
                };

                const filteredIntelItems = computed(() => {
                    const items = [];
                    const activeDims = targetDims[intelTab.value];
                    filteredLogs.value.forEach(log => {
                        const analysis = parseAnalysis(log.analysis_json);
                        for (const [key, val] of Object.entries(analysis)) {
                            if (activeDims.includes(key) && val && val.length > 2 && val !== '无' && val !== '空') {
                                items.push({ dimension: key, content: val, userName: log.user_name, date: log.log_date, log: log });
                            }
                        }
                    });
                    return items;
                });

                const intelCounts = computed(() => {
                    const counts = { risk: 0, opp: 0, market: 0 };
                    filteredLogs.value.forEach(log => {
                        const analysis = parseAnalysis(log.analysis_json);
                        for (const [key, val] of Object.entries(analysis)) {
                            if (val && val.length > 2 && val !== '无' && val !== '空') {
                                if (targetDims['risk'].includes(key)) counts.risk++;
                                if (targetDims['opp'].includes(key)) counts.opp++;
                                if (targetDims['market'].includes(key)) counts.market++;
                            }
                        }
                    });
                    return counts;
                });

                const kpi = computed(() => {
                    const l = filteredLogs.value;
                    let riskCount = 0;
                    let oppCount = 0;
                    let schoolMentions = 0;
                    
                    l.forEach(log => {
                        const analysis = parseAnalysis(log.analysis_json);
                        // Risk
                        const risks = [analysis['用户投诉'], analysis['销售流程阻碍点'], analysis['系统性与运营类问题']];
                        if (risks.some(r => r && r.length > 4)) riskCount++;
                        // Opp
                        const opps = [analysis['新业务与新模式反馈'], analysis['场景化需求与痛点']];
                        if (opps.some(r => r && r.length > 4)) oppCount++;
                        // School mentions check (simple regex)
                        if (/学校|高中|初中|小学/.test(log.content)) schoolMentions++;
                    });

                    return {
                        peopleCount: new Set(l.map(i => i.user_name)).size,
                        schoolCount: schoolMentions,
                        riskCount,
                        oppCount
                    };
                });

                const summarySentence = computed(() => {
                    if (kpi.value.riskCount > 0) return `今日需重点关注 ${kpi.value.riskCount} 项潜在风险，主要涉及用户投诉与流程阻碍，建议优先排查风险板块。`;
                    if (kpi.value.oppCount > 0) return `今日发现 ${kpi.value.oppCount} 个新业务机会，建议详细查看情报透视中的机会板块。`;
                    return `今日业务运行平稳，共收集 ${kpi.value.peopleCount} 份日报，市场反馈正常。`;
                });

                const hasTag = (log, type) => {
                    const analysis = parseAnalysis(log.analysis_json);
                    if (type === '投诉') return analysis['用户投诉'];
                    if (type === '阻碍') return analysis['销售流程阻碍点'];
                    if (type === '画像') return analysis['学校画像信息（规模/关键人/信息化水平/预算）'];
                    if (type === '机会') return analysis['新业务与新模式反馈'];
                    return false;
                };

                const getDigest = (log) => {
                    const analysis = parseAnalysis(log.analysis_json);
                    const allVals = Object.values(analysis).filter(v => v.length > 5);
                    return allVals.length > 0 ? allVals[0] : log.content.substring(0, 60) + '...';
                };

                // Actions
                const openDetail = (log) => { selectedLog.value = log; };
                const openDetailLog = (log) => { selectedLog.value = log; };
                const resetFilters = () => { filters.value = { dateRange: 'yesterday', department: '', search: '' }; };
                const jumpToIntelligence = (tab) => { intelTab.value = tab; currentView.value = 'intelligence'; };
                const filterByKeyword = (kw) => { currentView.value = 'explorer'; filters.value.search = kw; };
                
                // 手动拉取功能
                const isFetching = ref(false);
                const fetchProgress = ref({
                    phase: 'idle',
                    message: '',
                    current: 0,
                    total: 0,
                    current_user: ''
                });
                
                let progressInterval = null;
                
                const pollProgress = async () => {
                    try {
                        const response = await fetch('/api/progress');
                        const data = await response.json();
                        fetchProgress.value = data;
                        
                        if (!data.is_running && data.phase !== 'idle') {
                            // 任务结束
                            clearInterval(progressInterval);
                            progressInterval = null;
                            
                            if (data.phase === 'done') {
                                setTimeout(() => {
                                    isFetching.value = false;
                                    if (confirm('✅ ' + data.message + '\\n\\n是否立即刷新页面查看最新数据？')) {
                                        window.location.reload();
                                    }
                                }, 500);
                            } else if (data.phase === 'error') {
                                isFetching.value = false;
                                alert(data.message);
                            }
                        }
                    } catch (error) {
                        console.error('获取进度失败:', error);
                    }
                };
                
                const manualFetch = async () => {
                    if (isFetching.value) return;
                    isFetching.value = true;
                    fetchProgress.value = { phase: 'fetching', message: '正在启动...', current: 0, total: 0 };
                    
                    try {
                        const response = await fetch('/api/fetch');
                        const data = await response.json();
                        
                        // 开始轮询进度
                        progressInterval = setInterval(pollProgress, 1000);
                    } catch (error) {
                        isFetching.value = false;
                        alert('❌ 拉取请求失败: ' + error.message + '\\n\\n如果服务未启动，请先运行: python tita_service.py');
                    }
                };

                // Charts
                let dimChartInst = null;
                let wordCloudInst = null;

                const initCharts = () => {
                    if (currentView.value !== 'dashboard') return;
                    
                    nextTick(() => {
                        const dimEl = document.getElementById('chart-dimensions');
                        const wcEl = document.getElementById('chart-wordcloud');
                        
                        if (dimEl) {
                            if (dimChartInst) dimChartInst.dispose();
                            dimChartInst = echarts.init(dimEl);
                            
                            const dimCounts = {};
                            filteredLogs.value.forEach(log => {
                                const a = parseAnalysis(log.analysis_json);
                                for (const [k, v] of Object.entries(a)) {
                                    if (v && v.length > 5 && v !== '无') dimCounts[k] = (dimCounts[k] || 0) + 1;
                                }
                            });
                            
                            dimChartInst.setOption({
                                tooltip: { trigger: 'item' },
                                series: [{
                                    type: 'pie', radius: ['40%', '70%'],
                                    itemStyle: { borderRadius: 5 },
                                    data: Object.entries(dimCounts).map(([k, v]) => ({ value: v, name: k }))
                                }]
                            });

                             dimChartInst.on('click', (params) => {
                                // Jump to explorer searching for that dimension name
                                // But dimension name is a key, logs have keys mapped. 
                                // Better: jump to intelligence tab mapping the dimension
                                const riskDims = targetDims.risk;
                                const oppDims = targetDims.opp;
                                if (riskDims.includes(params.name)) jumpToIntelligence('risk');
                                else if (oppDims.includes(params.name)) jumpToIntelligence('opp');
                                else jumpToIntelligence('market');
                            });
                        }

                        if (wcEl && wordCloudData.length) {
                             if (wordCloudInst) wordCloudInst.dispose();
                             wordCloudInst = echarts.init(wcEl);
                             
                             wordCloudInst.setOption({
                                 tooltip: { show: true },
                                 series: [{
                                     type: 'wordCloud',
                                     shape: 'circle',
                                     left: 'center', top: 'center', width: '90%', height: '90%',
                                     sizeRange: [12, 50],
                                     rotationRange: [-45, 90],
                                     textStyle: {
                                         fontFamily: 'sans-serif',
                                         fontWeight: 'bold',
                                         color: () => 'rgb(' + [
                                             Math.round(Math.random() * 160),
                                             Math.round(Math.random() * 160),
                                             Math.round(Math.random() * 160)
                                         ].join(',') + ')'
                                     },
                                     data: wordCloudData
                                 }]
                             });
                             
                             wordCloudInst.on('click', (params) => {
                                 filterByKeyword(params.name);
                             });
                        }
                    });
                };

                watch(currentView, () => { if (currentView.value === 'dashboard') initCharts(); });
                onMounted(() => { initCharts(); });

                return {
                    currentView, intelTab, selectedLog, filters,
                    logs, generatedAt, yesterdayDate, uniqueDepartments,
                    filteredLogs, filteredIntelItems, kpi, intelCounts, summarySentence,
                    hasTag, getDigest, openDetail, openDetailLog, resetFilters, parseAnalysis,
                    jumpToIntelligence, filterByKeyword, isFetching, manualFetch, fetchProgress
                };
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

def extract_keywords(logs):
    """Simple keyword extraction for Chinese text without heavy NLP libs."""
    text_pool = ""
    for log in logs:
        text_pool += log['content'] + " "
        try:
            analysis = json.loads(log['analysis_json'])
            for v in analysis.values():
                text_pool += str(v) + " "
        except:
            pass
    
    # 1. Regex to find potential words (len > 1, Chinese characters)
    words = re.findall(r'[\u4e00-\u9fa5]{2,}', text_pool)
    
    # 2. Stop words list (expanded to filter out report template words)
    stop_words = set([
        # 日报模板固定词汇
        '今日', '昨日', '明日', '工作', '总结', '计划', '进展', '完成', '内容', '描述',
        '今日工作', '明日工作', '工作总结', '工作计划', '今日工作总结', '明日工作计划',
        '今天', '明天', '昨天', '本周', '上周', '本月', '上月',
        # OKR相关
        '进度', '目标', '关键', '结果', '指标', '达成', '执行',
        # 常用连接词/动词
        '沟通', '对接', '协调', '问题', '情况', '需要', '表示', '我们', '他们', 
        '以及', '虽然', '但是', '然后', '最后', '没有', '可以', '这个', '那个', 
        '一下', '目前', '正在', '已经', '进行', '拜访', '走访', '跟进', '处理',
        '反馈', '确认', '联系', '安排', '准备', '开展', '推进', '完善', '提升',
        '了解', '汇报', '整理', '梳理', '分析', '继续', '持续', '相关', '主要',
        '其他', '通过', '关于', '针对', '根据', '按照', '结合', '围绕', '针对',
        # 数字相关
        '一个', '两个', '三个', '第一', '第二', '第三',
        # 无意义短词
        '进行中', '已完成', '待完成', '无', '空', '暂无'
    ])
    
    # 3. Count
    counter = Counter([w for w in words if w not in stop_words])
    
    # Format for ECharts
    return [{"name": k, "value": v} for k, v in counter.most_common(60)]

def generate():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM daily_logs ORDER BY log_date DESC, user_name")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    if not rows:
        print("No data found in DB.")
        return

    yesterday_date = rows[0]['log_date'] if rows else ""
    keywords = extract_keywords(rows)
    
    data_payload = {
        "logs": rows,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "yesterday_date": yesterday_date,
        "word_cloud_data": keywords
    }

    final_html = html_template.replace("{{DATA_PLACEHOLDER}}", json.dumps(data_payload, ensure_ascii=False))

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"Dashboard generated: {os.path.abspath(OUTPUT_HTML)}")

if __name__ == "__main__":
    generate()
