各位领导：

以下为南网业务处唐标{{日期}}工作日报，烦请领导查收指正。

-----------------------------------

一、日报日期：{{日期}}

二、今日工作内容：

{{#each projects}}
{{index}}、项目名称：{{name}}
{{#each categories}}
{{#if (eq category "功能开发")}}
· {{category}}：
{{#each items}}
  - {{this}}
{{/each}}
{{else if (eq category "前端开发")}}
· {{category}}：
{{#each items}}
  - {{this}}
{{/each}}
{{else}}
· {{category}}：{{description}}
{{/if}}
{{/each}}

{{/each}}

三、明日（下周）工作计划：
{{#each plans}}
· {{plan}}
{{/each}}

四、重点项目里程碑情况：
{{#each milestones}}
· {{project}} - {{module}}：{{stage}}（{{percent}}%）
· 已完成：{{completed}}
· 下一步：{{next_step}}
· 风险点：{{risk}}
{{/each}}

-----------------------------------
山东浪潮数字服务有限公司
交通服务事业部 - 南网业务处
唐标
Tel: 13707490673
E-mail: tangbiao@inspur.com
{{日期}}
