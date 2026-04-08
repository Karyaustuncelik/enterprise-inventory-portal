IF COL_LENGTH('dbo.charts', 'groupFilterValue') IS NULL
BEGIN
    ALTER TABLE [dbo].[charts]
    ADD [groupFilterValue] NVARCHAR(400) NOT NULL
        CONSTRAINT [DF_charts_groupFilterValue] DEFAULT ('');
END;
