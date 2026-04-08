IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME = 'FieldParams'
)
BEGIN
    IF COL_LENGTH('dbo.FieldParams', 'IsActive') IS NULL
    BEGIN
        ALTER TABLE [dbo].[FieldParams]
        ADD [IsActive] BIT NOT NULL
            CONSTRAINT [DF_FieldParams_IsActive] DEFAULT (1);
    END;

    IF COL_LENGTH('dbo.FieldParams', 'IsActive') IS NOT NULL
    BEGIN
        EXEC(
            'UPDATE [dbo].[FieldParams]
             SET [IsActive] = CASE
                 WHEN FieldName = ''Status''
                      AND LOWER(LTRIM(RTRIM(ParamName))) LIKE ''%disposed%''
                     THEN 0
                 ELSE 1
             END
             WHERE FieldName = ''Status'';'
        );
    END;
END;
