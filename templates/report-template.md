各位领导：

以下为{{greeting}}{{日期}}工作日报，烦请领导查收指正。

-----------------------------------

一、日报日期：{{日期}}

二、今日工作内容：
{{#each projects}}
{{index}}、项目名称：{{name}}
{{#each items}}
· {{this}}
{{/each}}
{{/each}}
{{^projects}}当日无记录
{{/projects}}
三、明日（下周）工作计划：
{{#each plans}}
· {{plan}}
{{/each}}

四、重点项目里程碑情况：
{{#each milestones}}
· {{project}} - {{module}}
· 已完成：{{completed}}
· 下一步：{{next_step}}
· 风险点：{{risk}}
{{/each}}

-----------------------------------
{{company}}
{{department}}
{{name}}
Tel: {{phone}}
E-mail: {{email}}
{{日期}}
