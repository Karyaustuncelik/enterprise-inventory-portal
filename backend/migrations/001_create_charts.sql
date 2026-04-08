IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME = 'charts'
)
BEGIN
    CREATE TABLE [dbo].[charts] (
        [id] NVARCHAR(64) NOT NULL PRIMARY KEY,
        [title] NVARCHAR(200) NULL,
        [groupBy] NVARCHAR(100) NOT NULL,
        [groupFilterValue] NVARCHAR(400) NOT NULL
            CONSTRAINT [DF_charts_groupFilterValue] DEFAULT (''),
        [metric] NVARCHAR(10) NOT NULL,
        [filterBy] NVARCHAR(100) NOT NULL,
        [filterValue] NVARCHAR(200) NOT NULL,
        [created_at] DATETIME2(0) NOT NULL
            CONSTRAINT [DF_charts_created_at] DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(0) NOT NULL
            CONSTRAINT [DF_charts_updated_at] DEFAULT SYSUTCDATETIME(),
        CONSTRAINT [CK_charts_metric] CHECK ([metric] IN ('count', 'ratio'))
    );
END;
